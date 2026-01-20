#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include "Adafruit_VCNL4200.h"

// ESP-NOW
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_system.h>
#include <esp_mac.h>

// Storage + logging
#include <Preferences.h>
#include <LittleFS.h>

// HTTPS
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <time.h>

// ================= WIFI / WEBUI =================
const char* AP_SSID = "PuttingTracker";
const char* AP_PASS = "puttputt1";
static const uint8_t ESPNOW_CHANNEL = 6;   // MUST match sender

WebServer server(80);
Preferences prefs;

// ================= SENSOR =================
Adafruit_VCNL4200 vcnl4200;

// ================= COUNTERS =================
volatile uint32_t attempts = 0;
volatile uint32_t makes = 0;  // increments from ESP-NOW receiver

// ================= LED PINS =================
const int LED_RED_PIN   = 25;
const int LED_GREEN_PIN = 26;
const int LED_BLUE_PIN  = 27;

// ================= BUTTON =================
const int CAL_BTN_PIN = 33;   // momentary button to GND, uses INPUT_PULLUP

// ================= STATE =================
enum ReadyState { NO_BALL, BALL_READY, COOLDOWN };
ReadyState state = NO_BALL;

unsigned long lastAttemptMs = 0;
const unsigned long COOLDOWN_MS = 5000;  // 5 seconds

// ================= CALIBRATION =================
uint16_t baselineProx = 0;
uint16_t thresholdDelta = 250;
bool manualCalibrated = false;

// ================= BUTTON DEBOUNCE =================
const unsigned long DEBOUNCE_MS = 40;

// ================= DEBUG =================
bool debugSerial = true;
unsigned long lastDebugMs = 0;
const unsigned long DEBUG_PERIOD_MS = 200;

// ================= ESP-NOW PACKET =================
typedef struct __attribute__((packed)) {
  uint32_t seq;
  uint8_t  event;   // 1 = MAKE
} MakePacket;

volatile uint32_t lastMakeSeq = 0;

// ================= SESSION + LOGGING =================
static const char* LOG_FILE = "/attempts.csv";

bool sessionActive = false;
uint32_t sessionId = 0;
time_t sessionStartEpoch = 0;

float distanceFt = 8.0f;
String shotMode = "PUTT"; // PUTT or CHIP

// Correlate a make to the most recent attempt
bool pendingAttempt = false;
uint32_t pendingAttemptNum = 0;
time_t pendingAttemptEpoch = 0;
unsigned long pendingAttemptMs = 0;
const unsigned long MAKE_WINDOW_MS = 3500;

// Buffer rows for this session so we can push to Sheets on Stop
struct AttemptRow {
  uint32_t session_id;
  time_t start_epoch;
  time_t attempt_epoch;
  float distance_ft;
  String mode;
  uint32_t attempt_num;
  String result;     // MAKE or MISS
  time_t make_epoch; // 0 if miss
};

std::vector<AttemptRow> sessionRows;

// ================= HOME WIFI + SHEETS CONFIG =================
// Stored in Preferences so the device can be "set once"
String homeSsid = "";
String homePass = "";

// Your Apps Script Web App URL (set from WebUI or hardcode)
String sheetsUrl = "";     // e.g. https://script.google.com/macros/s/XXXX/exec
String sheetsSecret = "";  // simple shared secret, checked by Apps Script

// ================= HELPERS =================
String stateName(ReadyState s) {
  if (s == NO_BALL) return "NO_BALL";
  if (s == BALL_READY) return "BALL_READY";
  return "COOLDOWN";
}

void updateStatusLEDs() {
  digitalWrite(LED_RED_PIN,   state == NO_BALL);
  digitalWrite(LED_GREEN_PIN, state == BALL_READY);
  digitalWrite(LED_BLUE_PIN,  state == COOLDOWN);
}

uint16_t readProxAvg(int samples = 5) {
  uint32_t sum = 0;
  for (int i = 0; i < samples; i++) {
    sum += vcnl4200.readProxData();
    delay(5);
  }
  return sum / samples;
}

uint16_t measureBaseline() {
  uint32_t sum = 0;
  for (int i = 0; i < 30; i++) {
    sum += vcnl4200.readProxData();
    delay(20);
  }
  return sum / 30;
}

void applyProxConfig() {
  vcnl4200.setALSshutdown(true);
  vcnl4200.setProxShutdown(false);
  vcnl4200.setProxHD(true);
  vcnl4200.setProxLEDCurrent(VCNL4200_LED_I_200MA);
  vcnl4200.setProxIntegrationTime(VCNL4200_PS_IT_8T);
}

void runCalibration(bool manual) {
  baselineProx = measureBaseline();
  manualCalibrated = manual;

  state = NO_BALL;
  updateStatusLEDs();

  Serial.print(manual ? "[MANUAL CAL] " : "[AUTO CAL] ");
  Serial.print("baseline=");
  Serial.print(baselineProx);
  Serial.print(" delta=");
  Serial.println(thresholdDelta);
}

void printMacs() {
  uint8_t sta[6], ap[6];
  esp_read_mac(sta, ESP_MAC_WIFI_STA);
  esp_read_mac(ap,  ESP_MAC_WIFI_SOFTAP);

  Serial.printf("STA MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
                sta[0],sta[1],sta[2],sta[3],sta[4],sta[5]);

  Serial.printf("AP  MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
                ap[0],ap[1],ap[2],ap[3],ap[4],ap[5]);

  Serial.print("softAPmacAddress(): ");
  Serial.println(WiFi.softAPmacAddress());
}

void printChannel(const char* label) {
  uint8_t primary;
  wifi_second_chan_t second;
  esp_wifi_get_channel(&primary, &second);
  Serial.print(label);
  Serial.println(primary);
}

// ================= FILE LOGGING =================
void ensureCsvHeader() {
  if (!LittleFS.exists(LOG_FILE)) {
    File f = LittleFS.open(LOG_FILE, "w");
    f.println("session_id,start_epoch,attempt_epoch,distance_ft,mode,attempt_num,result,make_epoch");
    f.close();
  }
}

void appendCsvRow(const AttemptRow& r) {
  File f = LittleFS.open(LOG_FILE, "a");
  if (!f) {
    Serial.println("[LOG] Failed to open CSV for append");
    return;
  }
  f.print(r.session_id); f.print(",");
  f.print((uint32_t)r.start_epoch); f.print(",");
  f.print((uint32_t)r.attempt_epoch); f.print(",");
  f.print(r.distance_ft, 1); f.print(",");
  f.print(r.mode); f.print(",");
  f.print(r.attempt_num); f.print(",");
  f.print(r.result); f.print(",");
  if (r.make_epoch > 0) f.print((uint32_t)r.make_epoch);
  f.println();
  f.close();
}

// ================= TIME =================
bool syncTimeNtp(unsigned long timeoutMs = 15000) {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  unsigned long start = millis();
  time_t now;
  while (millis() - start < timeoutMs) {
    time(&now);
    if (now > 1700000000) { // sanity: after ~2023
      Serial.print("[TIME] NTP OK epoch=");
      Serial.println((uint32_t)now);
      return true;
    }
    delay(250);
  }
  Serial.println("[TIME] NTP sync failed");
  return false;
}

time_t nowEpochOrZero() {
  time_t now;
  time(&now);
  if (now > 1700000000) return now;
  return 0;
}

// ================= WIFI CONFIG STORAGE =================
void loadConfig() {
  prefs.begin("putt_cfg", true);
  homeSsid = prefs.getString("ssid", "");
  homePass = prefs.getString("pass", "");
  sheetsUrl = prefs.getString("surl", "");
  sheetsSecret = prefs.getString("ssec", "");
  sessionId = prefs.getUInt("sid", 0);
  prefs.end();
}

void saveConfig() {
  prefs.begin("putt_cfg", false);
  prefs.putString("ssid", homeSsid);
  prefs.putString("pass", homePass);
  prefs.putString("surl", sheetsUrl);
  prefs.putString("ssec", sheetsSecret);
  prefs.putUInt("sid", sessionId);
  prefs.end();
}

// ================= ESP-NOW RECEIVE =================
void onEspNowRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  if (len != (int)sizeof(MakePacket)) return;

  MakePacket pkt;
  memcpy(&pkt, data, sizeof(pkt));
  if (pkt.event != 1) return;

  if (pkt.seq == 0 || pkt.seq == lastMakeSeq) return;
  lastMakeSeq = pkt.seq;

  makes++;

  Serial.print("[ESPNOW MAKE] makes=");
  Serial.print(makes);
  Serial.print(" seq=");
  Serial.println(pkt.seq);

  // If we have a pending attempt and it is within the window, resolve as MAKE
  if (sessionActive && pendingAttempt) {
    unsigned long dt = millis() - pendingAttemptMs;
    if (dt <= MAKE_WINDOW_MS) {
      AttemptRow r;
      r.session_id = sessionId;
      r.start_epoch = sessionStartEpoch;
      r.attempt_epoch = pendingAttemptEpoch;
      r.distance_ft = distanceFt;
      r.mode = shotMode;
      r.attempt_num = pendingAttemptNum;
      r.result = "MAKE";
      r.make_epoch = nowEpochOrZero();

      sessionRows.push_back(r);
      appendCsvRow(r);

      pendingAttempt = false;
    }
  }
}

// ================= WIFI MODE CONTROL =================
// Start AP on fixed channel so ESP-NOW stays stable
void startApOnly() {
  WiFi.mode(WIFI_AP_STA); // keep STA available but not connected
  WiFi.disconnect(true, true);
  delay(200);

  bool ok = WiFi.softAP(AP_SSID, AP_PASS, ESPNOW_CHANNEL);
  Serial.print("[WIFI] AP started: ");
  Serial.println(ok ? "YES" : "NO");
  Serial.print("[WIFI] AP IP: ");
  Serial.println(WiFi.softAPIP());
  printChannel("[WIFI] Channel: ");
  Serial.print("[WIFI] softAP MAC: ");
  Serial.println(WiFi.softAPmacAddress());
}

// Temporarily connect STA for internet, then disconnect and return to AP channel 6
bool connectStaForSync(unsigned long timeoutMs = 15000) {
  if (homeSsid.length() == 0) {
    Serial.println("[WIFI] No home SSID saved");
    return false;
  }

  Serial.print("[WIFI] Connecting STA to ");
  Serial.println(homeSsid);

  WiFi.mode(WIFI_AP_STA);
  WiFi.begin(homeSsid.c_str(), homePass.c_str());

  unsigned long start = millis();
  while (millis() - start < timeoutMs) {
    if (WiFi.status() == WL_CONNECTED) {
      Serial.print("[WIFI] STA connected IP=");
      Serial.println(WiFi.localIP());
      return true;
    }
    delay(250);
  }

  Serial.println("[WIFI] STA connect timeout");
  return false;
}

void disconnectStaAfterSync() {
  Serial.println("[WIFI] Disconnecting STA and returning to AP channel 6");
  WiFi.disconnect(true, true);
  delay(300);

  // Restart AP on our fixed ESPNOW channel
  WiFi.softAPdisconnect(true);
  delay(200);
  WiFi.softAP(AP_SSID, AP_PASS, ESPNOW_CHANNEL);

  // ESP-NOW can be sensitive to WiFi changes, so re-init
  esp_now_deinit();
  delay(50);
  if (esp_now_init() == ESP_OK) {
    esp_now_register_recv_cb(onEspNowRecv);
    Serial.println("[ESPNOW] re-init OK");
  } else {
    Serial.println("[ESPNOW] re-init FAILED");
  }

  printChannel("[WIFI] Channel: ");
}

// ================= GOOGLE SHEETS PUSH =================
String jsonEscape(const String& s) {
  String out;
  out.reserve(s.length() + 10);
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    if (c == '\\' || c == '"') { out += '\\'; out += c; }
    else if (c == '\n') out += "\\n";
    else if (c == '\r') out += "\\r";
    else out += c;
  }
  return out;
}

bool pushSessionRowsToSheets() {
  if (sheetsUrl.length() == 0) {
    Serial.println("[SHEETS] No sheets URL saved");
    return false;
  }
  if (sheetsSecret.length() == 0) {
    Serial.println("[SHEETS] No secret saved");
    return false;
  }
  if (sessionRows.size() == 0) {
    Serial.println("[SHEETS] No rows to push");
    return true;
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[SHEETS] STA not connected");
    return false;
  }

  // Build JSON payload: { "secret":"...", "rows":[ [...], ... ] }
  String payload;
  payload.reserve(1024);
  payload += "{\"secret\":\"";
  payload += jsonEscape(sheetsSecret);
  payload += "\",\"rows\":[";

  for (size_t i = 0; i < sessionRows.size(); i++) {
    const AttemptRow& r = sessionRows[i];
    payload += "[";
    payload += String(r.session_id); payload += ",";
    payload += String((uint32_t)r.start_epoch); payload += ",";
    payload += String((uint32_t)r.attempt_epoch); payload += ",";
    payload += String(r.distance_ft, 1); payload += ",";
    payload += "\""; payload += jsonEscape(r.mode); payload += "\",";   // mode string
    payload += String(r.attempt_num); payload += ",";
    payload += "\""; payload += jsonEscape(r.result); payload += "\","; // result string
    payload += String((uint32_t)r.make_epoch);
    payload += "]";
    if (i + 1 < sessionRows.size()) payload += ",";
  }

  payload += "]}";

  // IMPORTANT: use the redirect-following function
  bool ok = postToSheets(sheetsUrl, payload);

  Serial.print("[SHEETS] pushSessionRowsToSheets result=");
  Serial.println(ok ? "OK" : "FAIL");

  return ok;
}


// Fallback: extract redirect target from HTML body
String extractHrefUrl(const String& html) {
  int i = html.indexOf("href=\"");
  if (i < 0) return "";
  i += 6; // len('href="')
  int j = html.indexOf("\"", i);
  if (j < 0) return "";
  return html.substring(i, j);
}

bool postToSheets(const String& sheetsUrl, const String& payloadJson) {
  if (sheetsUrl.length() < 10) {
    Serial.println("[SHEETS] No URL configured");
    return false;
  }

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  http.setTimeout(20000);

  Serial.print("[SHEETS] POST -> ");
  Serial.println(sheetsUrl);

  if (!http.begin(client, sheetsUrl)) {
    Serial.println("[SHEETS] http.begin failed");
    return false;
  }

  http.addHeader("Content-Type", "application/json");

  int code = http.POST((uint8_t*)payloadJson.c_str(), payloadJson.length());

  if (code <= 0) {
    Serial.print("[SHEETS] HTTP ");
    Serial.print(code);
    Serial.print(" ");
    Serial.println(http.errorToString(code));
    http.end();
    delay(250);
    return false;
  }

  Serial.print("[SHEETS] HTTP ");
  Serial.println(code);

  // For Apps Script, 302 is normal. Don't follow it.
  if (code == 301 || code == 302) {
    Serial.println("[SHEETS] Redirect received (normal for Apps Script). Treating as OK.");
    http.end();
    delay(250);
    return true;
  }

  // Only print body for non-redirect responses
  String resp = http.getString();
  Serial.print("[SHEETS] Resp: ");
  Serial.println(resp);

  http.end();
  delay(250);

  return (code >= 200 && code < 300);
}







// ================= SESSION CONTROL =================
void startSession() {
  sessionActive = true;
  sessionStartEpoch = nowEpochOrZero(); // might be 0 if never synced yet
  sessionRows.clear();

  pendingAttempt = false;

  Serial.print("[SESSION] START id=");
  Serial.print(sessionId);
  Serial.print(" epoch=");
  Serial.println((uint32_t)sessionStartEpoch);
}

bool stopSessionAndSync() {
  Serial.print("[SESSION] STOP id=");
  Serial.println(sessionId);

  sessionActive = false;

  // Resolve any pending attempt as MISS if it is still pending
  if (pendingAttempt) {
    AttemptRow r;
    r.session_id = sessionId;
    r.start_epoch = sessionStartEpoch;
    r.attempt_epoch = pendingAttemptEpoch;
    r.distance_ft = distanceFt;
    r.mode = shotMode;
    r.attempt_num = pendingAttemptNum;
    r.result = "MISS";
    r.make_epoch = 0;

    sessionRows.push_back(r);
    appendCsvRow(r);
    pendingAttempt = false;
  }

  // If no home wifi configured, just stop. Data remains in CSV.
  if (homeSsid.length() == 0 || sheetsUrl.length() == 0 || sheetsSecret.length() == 0) {
    Serial.println("[SESSION] Sync skipped (missing WiFi or Sheets config)");
    return false;
  }

  // Connect STA, NTP sync, push, then disconnect back to AP channel 6
  bool staOk = connectStaForSync();
  if (!staOk) {
    disconnectStaAfterSync();
    return false;
  }

  bool timeOk = syncTimeNtp();
  if (!timeOk) {
    // keep going, but timestamps might be 0
  }

  bool pushOk = pushSessionRowsToSheets();

  disconnectStaAfterSync();
  return pushOk;
}

// ================= WEB PAGE =================
String wifiStatusString() {
  if (homeSsid.length() == 0) return "Not configured";
  return "Configured (will connect on Stop)";
}

String page(uint16_t prox_unused) {
  String html;
  html += "<html><head><meta name='viewport' content='width=device-width'>";
  html += "<title>Total Putt Counter</title>";
  html += "<style>body{font-family:Arial;margin:16px} input{width:100%;padding:8px} button{padding:10px 12px;margin:4px 0} .row{margin:6px 0}</style>";
  html += "</head><body>";

  html += "<h2>Total Putt Counter</h2>";

  html += "<div class='row'><b>Attempts:</b> <span id='attempts'>0</span></div>";
  html += "<div class='row'><b>Makes:</b> <span id='makes'>0</span></div>";
  html += "<div class='row'><b>Make %:</b> <span id='pct'>0.0</span>%</div>";

  html += "<hr>";
  html += "<h3>Session</h3>";
  html += "<div class='row'><b>Status:</b> <span id='sessionStatus'>STOPPED</span></div>";
  html += "<div class='row'><b>Session ID:</b> <span id='sessionId'>0</span></div>";
  html += "<div class='row'><b>Distance:</b> <span id='distanceFt'>8.0</span> ft</div>";
  html += "<div class='row'><b>Mode:</b> <span id='mode'>PUTT</span></div>";

  html += "<p>";
  html += "<a href='/start'>Start Session</a> | ";
  html += "<a href='/stop'>Stop + Sync</a> | ";
  html += "<a href='/sync'>Sync Now</a>";
  html += "</p>";

  html += "<p><a href='/download'>Download CSV</a></p>";

  html += "<p><b>Presets:</b><br>";
  html += "<a href='/set?d=4&mode=PUTT'>4ft PUTT</a> | ";
  html += "<a href='/set?d=8&mode=PUTT'>8ft PUTT</a> | ";
  html += "<a href='/set?d=12&mode=PUTT'>12ft PUTT</a><br>";
  html += "<a href='/set?d=8&mode=CHIP'>8ft CHIP</a> | ";
  html += "<a href='/set?d=12&mode=CHIP'>12ft CHIP</a>";
  html += "</p>";

  html += "<hr>";
  html += "<h3>Wi-Fi + Google Sheets</h3>";
  html += "<div class='row'><b>Home Wi-Fi:</b> <span id='wifiStatus'>Not configured</span></div>";

  html += "<form action='/savecfg' method='POST'>";
  html += "<div class='row'>SSID:<br><input name='ssid' id='ssidBox'></div>";
  html += "<div class='row'>Password:<br><input name='pass' type='password' placeholder='(leave blank to keep saved)'></div>";
  html += "<div class='row'>Sheets URL:<br><input name='surl' id='surlBox'></div>";
  html += "<div class='row'>Secret:<br><input name='ssec' id='ssecBox'></div>";
  html += "<div class='row'><input type='submit' value='Save Config'></div>";
  html += "</form>";
  html += "<p style='font-size:12px;'>Note: sync happens after Stop to keep ESP-NOW stable during sessions.</p>";

  html += "<hr>";
  html += "<h3>Sensor</h3>";
  html += "<div class='row'><b>Prox(avg):</b> <span id='prox'>0</span></div>";
  html += "<div class='row'><b>Baseline:</b> <span id='baseline'>0</span></div>";
  html += "<div class='row'><b>Delta:</b> <span id='delta'>0</span></div>";
  html += "<div class='row'><b>Threshold:</b> <span id='threshold'>0</span></div>";
  html += "<div class='row'><b>Ball Present:</b> <span id='present'>NO</span></div>";
  html += "<div class='row'><b>State:</b> <span id='state'>NO_BALL</span></div>";

  html += "<hr>";
  html += "<p><a href='/calibrate'>Manual Calibrate (NO ball)</a></p>";
  html += "<p><a href='/delta?d=100'>Delta 100</a> | <a href='/delta?d=200'>200</a> | <a href='/delta?d=300'>300</a> | <a href='/delta?d=500'>500</a></p>";
  html += "<p><a href='/reset' style='color:#b00;'>Reset Counters</a></p>";

  html += "<hr>";
  html += "<div class='row'><b>AP IP:</b> <span id='apIp'>0.0.0.0</span></div>";
  html += "<div class='row'><b>AP MAC:</b> <span id='apMac'>--</span></div>";

  // ---- JS polling ----
  html += R"rawliteral(
<script>
async function refresh() {
  try {
    const r = await fetch('/api', {cache:'no-store'});
    const j = await r.json();

    document.getElementById('attempts').textContent = j.attempts;
    document.getElementById('makes').textContent = j.makes;
    document.getElementById('pct').textContent = j.pct;

    document.getElementById('prox').textContent = j.prox;
    document.getElementById('baseline').textContent = j.baseline;
    document.getElementById('delta').textContent = j.delta;
    document.getElementById('threshold').textContent = j.threshold;
    document.getElementById('present').textContent = j.present ? 'YES' : 'NO';
    document.getElementById('state').textContent = j.state;

    document.getElementById('sessionStatus').textContent = j.sessionActive ? 'ACTIVE' : 'STOPPED';
    document.getElementById('sessionId').textContent = j.sessionId;
    document.getElementById('distanceFt').textContent = j.distanceFt;
    document.getElementById('mode').textContent = j.mode;

    document.getElementById('wifiStatus').textContent = j.wifiConfigured ? 'Configured (sync on Stop)' : 'Not configured';

    document.getElementById('apIp').textContent = j.apIp;
    document.getElementById('apMac').textContent = j.apMac;

    // Only set defaults into text boxes once, so we don't overwrite what you're typing
    if (!window._filledDefaults) {
      document.getElementById('ssidBox').value = '';
      document.getElementById('surlBox').value = '';
      document.getElementById('ssecBox').value = '';
      window._filledDefaults = true;
    }
  } catch (e) {
    // ignore transient errors
  }
}

refresh();
setInterval(refresh, 1000);
</script>
)rawliteral";

  html += "</body></html>";
  return html;
}


void handleRoot() {
  server.send(200, "text/html", page(readProxAvg()));
}

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  delay(300);

  Wire.begin(21, 22);

  // LEDs
  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_BLUE_PIN, OUTPUT);

  // Button
  pinMode(CAL_BTN_PIN, INPUT_PULLUP);

  // Sensor init
  if (!vcnl4200.begin()) {
    Serial.println("VCNL4200 not found! Check wiring.");
    while (1) delay(10);
  }
  Serial.println("VCNL4200 found!");
  applyProxConfig();

  // Filesystem
  if (!LittleFS.begin(true)) {
    Serial.println("LittleFS mount failed!");
  } else {
    Serial.println("LittleFS mounted");
    ensureCsvHeader();
  }

  loadConfig();

  // Auto baseline on boot
  runCalibration(false);

  // Start AP on fixed channel so ESP-NOW stays stable
  startApOnly();

  printMacs();

  // ESP-NOW init (receiver)
  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW init failed!");
    while (1) delay(10);
  }
  esp_now_register_recv_cb(onEspNowRecv);
  Serial.println("ESP-NOW receiver ready");

  // Web routes
  server.on("/", handleRoot);

  server.on("/calibrate", []() {
    runCalibration(true);
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/delta", []() {
    if (server.hasArg("d")) {
      uint16_t d = (uint16_t)server.arg("d").toInt();
      if (d > 0 && d < 5000) thresholdDelta = d;
    }
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/reset", []() {
    attempts = 0;
    makes = 0;
    lastMakeSeq = 0;
    thresholdDelta = 250;
    runCalibration(false);

    pendingAttempt = false;
    sessionRows.clear();

    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/set", []() {
    if (server.hasArg("d")) distanceFt = server.arg("d").toFloat();
    if (server.hasArg("mode")) shotMode = server.arg("mode");
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/start", []() {
    // Start a new session id
    sessionId++;
    saveConfig();

    startSession();
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/stop", []() {
    bool ok = stopSessionAndSync();
    server.send(200, "text/plain", ok ? "Stopped. Sync OK." : "Stopped. Sync failed or skipped.");
  });

  server.on("/sync", []() {
    bool ok = stopSessionAndSync();
    server.send(200, "text/plain", ok ? "Sync OK." : "Sync failed or skipped.");
  });

  server.on("/download", []() {
    if (!LittleFS.exists(LOG_FILE)) {
      server.send(404, "text/plain", "No log file yet.");
      return;
    }
    File f = LittleFS.open(LOG_FILE, "r");
    server.streamFile(f, "text/csv");
    f.close();
  });

  server.on("/savecfg", HTTP_POST, []() {
    homeSsid = server.arg("ssid");
    String passIn = server.arg("pass");
    if (passIn.length() > 0) homePass = passIn; // only overwrite if user typed a new one
    sheetsUrl = server.arg("surl");
    sheetsSecret = server.arg("ssec");

    saveConfig();

    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/api", []() {
    uint16_t prox = readProxAvg();
    uint16_t threshold = baselineProx + thresholdDelta;
    bool present = prox > threshold;

    float pct = (attempts == 0) ? 0.0f : (100.0f * (float)makes / (float)attempts);

    String json = "{";
    json += "\"attempts\":" + String((uint32_t)attempts) + ",";
    json += "\"makes\":" + String((uint32_t)makes) + ",";
    json += "\"pct\":" + String(pct, 1) + ",";
    json += "\"prox\":" + String(prox) + ",";
    json += "\"baseline\":" + String(baselineProx) + ",";
    json += "\"delta\":" + String(thresholdDelta) + ",";
    json += "\"threshold\":" + String(threshold) + ",";
    json += "\"present\":" + String(present ? "true" : "false") + ",";
    json += "\"state\":\"" + stateName(state) + "\",";
    json += "\"sessionActive\":" + String(sessionActive ? "true" : "false") + ",";
    json += "\"sessionId\":" + String(sessionId) + ",";
    json += "\"distanceFt\":" + String(distanceFt, 1) + ",";
    json += "\"mode\":\"" + shotMode + "\",";
    json += "\"wifiConfigured\":" + String((homeSsid.length() > 0) ? "true" : "false") + ",";
    json += "\"apIp\":\"" + WiFi.softAPIP().toString() + "\",";
    json += "\"apMac\":\"" + WiFi.softAPmacAddress() + "\"";
    json += "}";

    server.send(200, "application/json", json);
  });


  server.begin();
  Serial.println("Web server started");
}

// ================= LOOP =================
void loop() {
  server.handleClient();

  // ----- Button handling -----
  static int lastReading = HIGH;
  static int stableState = HIGH;
  static unsigned long lastChangeMs = 0;

  int reading = digitalRead(CAL_BTN_PIN);
  if (reading != lastReading) {
    lastChangeMs = millis();
    lastReading = reading;
  }

  if ((millis() - lastChangeMs) > DEBOUNCE_MS) {
    if (reading != stableState) {
      stableState = reading;
      if (stableState == LOW) {
        Serial.println("[BTN] calibrate");
        runCalibration(true);
      }
    }
  }

  // ----- Putt attempt logic -----
  uint16_t prox = readProxAvg();
  uint16_t threshold = baselineProx + thresholdDelta;
  bool present = prox > threshold;
  unsigned long now = millis();

  if (state == COOLDOWN) {
    if (now - lastAttemptMs >= COOLDOWN_MS) {
      state = present ? BALL_READY : NO_BALL;
      updateStatusLEDs();
    }
  } else {
    if (state == NO_BALL && present) {
      state = BALL_READY;
      updateStatusLEDs();
    } else if (state == BALL_READY && !present) {
      attempts++;
      lastAttemptMs = now;
      state = COOLDOWN;
      updateStatusLEDs();

      Serial.print("[ATTEMPT] attempts=");
      Serial.println(attempts);

      // Open a pending window to associate a make packet with this attempt
      if (sessionActive) {
        pendingAttempt = true;
        pendingAttemptNum = attempts;
        pendingAttemptEpoch = nowEpochOrZero();
        pendingAttemptMs = millis();
      }
    }
  }

  // If the pending window expires without a make, log a MISS
  if (sessionActive && pendingAttempt) {
    if (millis() - pendingAttemptMs > MAKE_WINDOW_MS) {
      AttemptRow r;
      r.session_id = sessionId;
      r.start_epoch = sessionStartEpoch;
      r.attempt_epoch = pendingAttemptEpoch;
      r.distance_ft = distanceFt;
      r.mode = shotMode;
      r.attempt_num = pendingAttemptNum;
      r.result = "MISS";
      r.make_epoch = 0;

      sessionRows.push_back(r);
      appendCsvRow(r);

      pendingAttempt = false;
    }
  }

  // ----- Debug -----
  if (debugSerial && now - lastDebugMs > DEBUG_PERIOD_MS) {
    lastDebugMs = now;
    Serial.print("prox=");
    Serial.print(prox);
    Serial.print(" baseline=");
    Serial.print(baselineProx);
    Serial.print(" makes=");
    Serial.print(makes);
    Serial.print(" attempts=");
    Serial.print(attempts);
    Serial.print(" state=");
    Serial.print(stateName(state));
    Serial.print(" session=");
    Serial.println(sessionActive ? "ON" : "OFF");
  }
}
