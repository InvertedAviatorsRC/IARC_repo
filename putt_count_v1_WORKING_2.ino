/*
  Total Putt Counter v1
  Correct architecture: sync runs in loop() state machine (not inside HTTP route handlers)

  Hardware
  - ESP32-WROOM-32
  - Adafruit VCNL4200 (I2C)
  - 3 LEDs (RED/GREEN/BLUE) each with resistor
  - Calibrate button to GND (INPUT_PULLUP)

  Features
  - Attempts counted when ball leaves spot (BALL_READY -> !present)
  - Makes incremented via ESP-NOW from made-putt module
  - Web UI over SoftAP on fixed channel (ESPNOW_CHANNEL)
  - Optional LittleFS session logging + pending sync retry
  - Google Sheets upload via Apps Script /exec (HTTP 302 is normal, treated as OK)

  Important
  - Sync (STA connect + HTTPS post + teardown) is NOT performed inside HTTP callbacks.
  - HTTP callbacks schedule a sync; loop() executes it safely.
*/

#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <vector>

#include "Adafruit_VCNL4200.h"

// ESP-NOW
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_system.h>
#include <esp_mac.h>

// ========== Toggle LittleFS ==========
#define USE_LITTLEFS 1
#if USE_LITTLEFS
  #include <LittleFS.h>
#endif

// ================= WIFI / WEBUI =================
const char* AP_SSID = "PuttingTracker";
const char* AP_PASS = "puttputt1";
static const uint8_t ESPNOW_CHANNEL = 6;

WebServer server(80);

// STA credentials (set via /setwifi and persisted if LittleFS enabled)
String staSsid = "NeveNet";
String staPass = "N3V3N3T!";

// Apps Script URL + secret (set via /setsheets and persisted if LittleFS enabled)
String sheetsUrl = "https://script.google.com/macros/s/AKfycbw_0quPvB7Zhs4JWJD39BZsbdVPRxrdXwHdwB5SKq_sSxyTnO9ejJWBmwmqgb_LRob14Q/exec";          // example: https://script.google.com/macros/s/XXXX/exec
String sheetsSecret = "puttputt";

// ================= SENSOR =================
Adafruit_VCNL4200 vcnl4200;

// ================= COUNTERS =================
volatile uint32_t attempts = 0;
volatile uint32_t makes = 0;

// ================= LED PINS =================
const int LED_RED_PIN   = 25;
const int LED_GREEN_PIN = 26;
const int LED_BLUE_PIN  = 27;

// ================= BUTTON =================
const int CAL_BTN_PIN = 33;   // momentary to GND, INPUT_PULLUP

// ================= STATE =================
enum ReadyState { NO_BALL, BALL_READY, COOLDOWN };
ReadyState state = NO_BALL;

unsigned long lastAttemptMs = 0;
const unsigned long COOLDOWN_MS = 5000;

// ================= CALIBRATION =================
uint16_t baselineProx = 0;
uint16_t thresholdDelta = 250;
bool manualCalibrated = false;

// ================= BUTTON DEBOUNCE =================
const unsigned long DEBOUNCE_MS = 40;

// ================= DEBUG =================
bool debugSerial = true;
unsigned long lastDebugMs = 0;
const unsigned long DEBUG_PERIOD_MS = 250;

// ================= MODE / DIST =================
String shotMode = "PUTT";
float distanceFt = 8.0f;

// ================= SESSION LOGGING (RAM) =================
struct AttemptRow {
  uint32_t session_id;
  uint32_t attempt_num;

  uint32_t start_ms;
  uint32_t attempt_ms;
  uint32_t make_ms;   // 0 if none

  float distance_ft;
  String mode;        // PUTT / CHIP
  String result;      // MISS / MAKE
};

bool sessionActive = false;
uint32_t sessionId = 0;
uint32_t sessionStartMs = 0;
uint32_t attemptCounter = 0;

std::vector<AttemptRow> sessionRows;

// ================= ESP-NOW PACKET =================
typedef struct __attribute__((packed)) {
  uint32_t seq;
  uint8_t  event;   // 1 = MAKE
} MakePacket;

volatile uint32_t lastMakeSeq = 0;

// ================= LittleFS paths =================
#if USE_LITTLEFS
static const char* SESS_DIR = "/sessions";
static const char* CFG_PATH = "/config.txt";
#endif

// ================= SYNC STATE MACHINE =================
enum SyncRequestType { SYNC_NONE, SYNC_STOP_AND_UPLOAD_CURRENT, SYNC_UPLOAD_PENDING };
volatile SyncRequestType syncRequest = SYNC_NONE;

enum SyncState {
  SYNC_IDLE,
  SYNC_PREP,           // wait a moment after responding to HTTP
  SYNC_STOP_SERVER,
  SYNC_WIFI_TO_STA,
  SYNC_CONNECT_STA,
  SYNC_NTP,
  SYNC_POST,
  SYNC_POST_PENDING,
  SYNC_RETURN_TO_AP,
  SYNC_RESTART_SERVER,
  SYNC_DONE
};

SyncState syncState = SYNC_IDLE;
unsigned long syncStateMs = 0;

bool syncOk = false;
uint32_t syncEpochNow = 0;

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
  return (uint16_t)(sum / (uint32_t)samples);
}

uint16_t measureBaseline() {
  uint32_t sum = 0;
  for (int i = 0; i < 30; i++) {
    sum += vcnl4200.readProxData();
    delay(20);
  }
  return (uint16_t)(sum / 30);
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

void printChannel(const char* label) {
  uint8_t primary;
  wifi_second_chan_t second;
  esp_wifi_get_channel(&primary, &second);
  Serial.print(label);
  Serial.println(primary);
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

String jsonEscape(const String& in) {
  String out;
  out.reserve(in.length() + 8);
  for (size_t i = 0; i < in.length(); i++) {
    char c = in[i];
    if (c == '\\') out += "\\\\";
    else if (c == '"') out += "\\\"";
    else if (c == '\n') out += "\\n";
    else if (c == '\r') out += "\\r";
    else if (c == '\t') out += "\\t";
    else out += c;
  }
  return out;
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

  if (sessionActive && !sessionRows.empty()) {
    AttemptRow& last = sessionRows.back();
    if (last.result == "MISS") {
      last.result = "MAKE";
      last.make_ms = (uint32_t)millis();
    }
  }

  Serial.print("[ESPNOW MAKE] makes=");
  Serial.print(makes);
  Serial.print(" seq=");
  Serial.println(pkt.seq);
}

bool initEspNowReceiver() {
  esp_now_deinit();
  delay(30);

  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESPNOW] init failed");
    return false;
  }
  esp_now_register_recv_cb(onEspNowRecv);
  Serial.println("[ESPNOW] receiver ready");
  return true;
}

void deinitEspNow() {
  esp_now_deinit();
  delay(30);
}

// ================= TIME (NTP) =================
bool ensureTimeNtp(uint32_t& epochOut) {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  time_t now = 0;

  for (int i = 0; i < 50; i++) {
    delay(200);
    time(&now);
    if (now > 1700000000) break;
  }

  if (now < 1700000000) {
    Serial.println("[TIME] NTP failed");
    return false;
  }

  epochOut = (uint32_t)now;
  Serial.print("[TIME] NTP OK epoch=");
  Serial.println(epochOut);
  return true;
}

// ================= GOOGLE SHEETS POST =================
bool postToSheets(const String& url, const String& payloadJson) {
  if (url.length() < 10) {
    Serial.println("[SHEETS] No URL configured");
    return false;
  }

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  http.setTimeout(20000);

  Serial.print("[SHEETS] POST -> ");
  Serial.println(url);

  if (!http.begin(client, url)) {
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
    delay(200);
    return false;
  }

  Serial.print("[SHEETS] HTTP ");
  Serial.println(code);

  // Apps Script sometimes returns 302 for /exec. Treat as OK.
  if (code == 301 || code == 302) {
    Serial.println("[SHEETS] Redirect received (normal for Apps Script). Treating as OK.");
    http.end();
    delay(200);
    return true;
  }

  String resp = http.getString();
  Serial.print("[SHEETS] Resp: ");
  Serial.println(resp);

  http.end();
  delay(200);

  return (code >= 200 && code < 300);
}

// ================= SESSION CONTROL =================
void startSession() {
  sessionActive = true;
  sessionId++;
  sessionStartMs = (uint32_t)millis();
  attemptCounter = 0;
  lastMakeSeq = 0;

  attempts = 0;
  makes = 0;

  sessionRows.clear();

  Serial.print("[SESSION] START id=");
  Serial.println(sessionId);
}

void stopSessionLocalOnly() {
  sessionActive = false;

  Serial.print("[SESSION] STOP id=");
  Serial.println(sessionId);

  // Save locally if enabled
#if USE_LITTLEFS
  // implemented below
#endif
}

// ================= LittleFS (optional) =================
#if USE_LITTLEFS
void ensureSessionDir() {
  if (!LittleFS.exists(SESS_DIR)) LittleFS.mkdir(SESS_DIR);
}

String sessionPathCsv(uint32_t sid) {
  return String(SESS_DIR) + "/sess_" + String(sid) + ".csv";
}

String sessionPathUp(uint32_t sid) {
  return String(SESS_DIR) + "/sess_" + String(sid) + ".up";
}

bool writeUploadedFlag(uint32_t sid, bool uploaded) {
  ensureSessionDir();
  File f = LittleFS.open(sessionPathUp(sid), "w");
  if (!f) return false;
  f.print(uploaded ? "1" : "0");
  f.close();
  return true;
}

bool readUploadedFlag(uint32_t sid, bool& uploadedOut) {
  String p = sessionPathUp(sid);
  if (!LittleFS.exists(p)) return false;
  File f = LittleFS.open(p, "r");
  if (!f) return false;
  String s = f.readString();
  f.close();
  s.trim();
  uploadedOut = (s == "1");
  return true;
}

bool saveSessionToLittleFS(uint32_t sid) {
  ensureSessionDir();

  File f = LittleFS.open(sessionPathCsv(sid), "w");
  if (!f) {
    Serial.println("[FS] Failed to open session CSV for write");
    return false;
  }

  f.println("session_id,start_ms,attempt_ms,distance_ft,mode,attempt_num,result,make_ms");

  for (size_t i = 0; i < sessionRows.size(); i++) {
    const AttemptRow& r = sessionRows[i];
    f.print(r.session_id); f.print(",");
    f.print(r.start_ms); f.print(",");
    f.print(r.attempt_ms); f.print(",");
    f.print(r.distance_ft, 1); f.print(",");
    f.print(r.mode); f.print(",");
    f.print(r.attempt_num); f.print(",");
    f.print(r.result); f.print(",");
    f.println(r.make_ms);
  }

  f.close();
  writeUploadedFlag(sid, false);

  Serial.print("[FS] Saved session ");
  Serial.print(sid);
  Serial.print(" rows=");
  Serial.println((uint32_t)sessionRows.size());
  return true;
}

void markSessionUploaded(uint32_t sid) {
  writeUploadedFlag(sid, true);
  Serial.print("[FS] Mark uploaded session ");
  Serial.println(sid);
}

int countPendingSessions() {
  ensureSessionDir();
  File dir = LittleFS.open(SESS_DIR);
  if (!dir || !dir.isDirectory()) return 0;

  int pending = 0;
  File f = dir.openNextFile();
  while (f) {
    String name = f.name();
    f.close();

    if (name.endsWith(".up")) {
      int a = name.indexOf("sess_");
      int b = name.lastIndexOf(".up");
      if (a >= 0 && b > a) {
        uint32_t sid = (uint32_t)name.substring(a + 5, b).toInt();
        bool up = false;
        if (readUploadedFlag(sid, up) && !up) pending++;
      }
    }
    f = dir.openNextFile();
  }
  return pending;
}

bool readSessionCsvToRows(uint32_t sid, std::vector<AttemptRow>& outRows) {
  outRows.clear();
  String path = sessionPathCsv(sid);
  if (!LittleFS.exists(path)) return false;

  File f = LittleFS.open(path, "r");
  if (!f) return false;

  f.readStringUntil('\n'); // header

  while (f.available()) {
    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;

    std::vector<String> parts;
    parts.reserve(8);

    int start = 0;
    while (true) {
      int comma = line.indexOf(',', start);
      if (comma < 0) {
        parts.push_back(line.substring(start));
        break;
      }
      parts.push_back(line.substring(start, comma));
      start = comma + 1;
    }
    if (parts.size() < 8) continue;

    AttemptRow r;
    r.session_id  = (uint32_t)parts[0].toInt();
    r.start_ms    = (uint32_t)parts[1].toInt();
    r.attempt_ms  = (uint32_t)parts[2].toInt();
    r.distance_ft = parts[3].toFloat();
    r.mode        = parts[4];
    r.attempt_num = (uint32_t)parts[5].toInt();
    r.result      = parts[6];
    r.make_ms     = (uint32_t)parts[7].toInt();

    outRows.push_back(r);
  }

  f.close();
  return true;
}

bool pushRowsToSheets(const std::vector<AttemptRow>& rows, uint32_t epochNow) {
  if (rows.empty()) return true;
  if (sheetsUrl.length() < 10) return false;
  if (WiFi.status() != WL_CONNECTED) return false;

  uint32_t startMs = rows[0].start_ms;
  uint32_t nowMs = (uint32_t)millis();
  uint32_t startEpoch = epochNow - (uint32_t)((nowMs - startMs) / 1000UL);

  String payload;
  payload.reserve(2048);

  payload += "{\"secret\":\"";
  payload += jsonEscape(sheetsSecret);
  payload += "\",\"rows\":[";

  for (size_t i = 0; i < rows.size(); i++) {
    const AttemptRow& r = rows[i];
    uint32_t attemptEpoch = startEpoch + (uint32_t)((r.attempt_ms - startMs) / 1000UL);
    uint32_t makeEpoch = 0;
    if (r.make_ms > 0) makeEpoch = startEpoch + (uint32_t)((r.make_ms - startMs) / 1000UL);

    payload += "[";
    payload += String(r.session_id); payload += ",";
    payload += String(startEpoch); payload += ",";
    payload += String(attemptEpoch); payload += ",";
    payload += String(r.distance_ft, 1); payload += ",";
    payload += "\""; payload += jsonEscape(r.mode); payload += "\",";
    payload += String(r.attempt_num); payload += ",";
    payload += "\""; payload += jsonEscape(r.result); payload += "\",";
    payload += String(makeEpoch);
    payload += "]";

    if (i + 1 < rows.size()) payload += ",";
  }

  payload += "]}";

  return postToSheets(sheetsUrl, payload);
}

bool pushCurrentSessionFromRam(uint32_t epochNow) {
  if (sessionRows.empty()) {
    Serial.println("[SHEETS] No rows in current session");
    return true;
  }
  bool ok = pushRowsToSheets(sessionRows, epochNow);
  Serial.print("[SHEETS] push current session result=");
  Serial.println(ok ? "OK" : "FAIL");
  return ok;
}

bool pushPendingSessions(uint32_t epochNow) {
  ensureSessionDir();
  File dir = LittleFS.open(SESS_DIR);
  if (!dir || !dir.isDirectory()) return true;

  int pending = 0;
  int uploadedNow = 0;

  File f = dir.openNextFile();
  while (f) {
    String name = f.name();
    f.close();

    if (name.endsWith(".up")) {
      int a = name.indexOf("sess_");
      int b = name.lastIndexOf(".up");
      if (a >= 0 && b > a) {
        uint32_t sid = (uint32_t)name.substring(a + 5, b).toInt();
        bool up = false;
        if (readUploadedFlag(sid, up) && !up) {
          pending++;

          std::vector<AttemptRow> rows;
          if (readSessionCsvToRows(sid, rows)) {
            bool ok = pushRowsToSheets(rows, epochNow);
            if (ok) {
              markSessionUploaded(sid);
              uploadedNow++;
            }
          }
        }
      }
    }
    f = dir.openNextFile();
  }

  Serial.print("[FS] Pending=");
  Serial.print(pending);
  Serial.print(" uploaded_now=");
  Serial.println(uploadedNow);

  return true;
}

// Config persistence
void saveConfig() {
  File f = LittleFS.open(CFG_PATH, "w");
  if (!f) return;

  f.println(String("staSsid=") + staSsid);
  f.println(String("staPass=") + staPass);
  f.println(String("sheetsUrl=") + sheetsUrl);
  f.println(String("sheetsSecret=") + sheetsSecret);

  f.close();
  Serial.println("[FS] Config saved");
}

void loadConfig() {
  if (!LittleFS.exists(CFG_PATH)) return;
  File f = LittleFS.open(CFG_PATH, "r");
  if (!f) return;

  while (f.available()) {
    String line = f.readStringUntil('\n');
    line.trim();
    if (!line.length()) continue;

    int eq = line.indexOf('=');
    if (eq < 0) continue;

    String k = line.substring(0, eq);
    String v = line.substring(eq + 1);

    if (k == "staSsid") staSsid = v;
    else if (k == "staPass") staPass = v;
    else if (k == "sheetsUrl") sheetsUrl = v;
    else if (k == "sheetsSecret") sheetsSecret = v;
  }

  f.close();
  Serial.println("[FS] Config loaded");
}
#endif // USE_LITTLEFS

// ================= WIFI MODE HELPERS (used by sync state machine) =================
bool startApOnChannel() {
  WiFi.mode(WIFI_AP_STA);
  bool ok = WiFi.softAP(AP_SSID, AP_PASS, ESPNOW_CHANNEL);
  delay(200);
  return ok;
}

bool connectSta() {
  if (staSsid.length() == 0) {
    Serial.println("[WIFI] No STA SSID configured");
    return false;
  }

  Serial.print("[WIFI] Connecting STA to ");
  Serial.println(staSsid);

  WiFi.begin(staSsid.c_str(), staPass.c_str());

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < 15000) {
    delay(250);
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] STA connect FAILED");
    return false;
  }

  Serial.print("[WIFI] STA connected IP=");
  Serial.println(WiFi.localIP());
  return true;
}

void disconnectSta() {
  WiFi.disconnect(false, false);
  delay(200);
}

// ================= WEB PAGE =================
String page() {
  String html;
  html += "<!doctype html><html><head>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1'>";
  html += "<style>body{font-family:Arial;margin:16px} .row{margin:6px 0} .k{font-weight:bold}</style>";
  html += "</head><body>";

  html += "<h2>Total Putt Counter</h2>";

  html += "<div id='banner' style='display:none; padding:10px; background:#fff3cd; border:1px solid #ffeeba; margin:10px 0;'>";
  html += "Syncing to Google Sheets…";
  html += "</div>";


  html += "<div class='row'><span class='k'>Session:</span> <span id='sess'>...</span></div>";
  html += "<div class='row'><span class='k'>Attempts:</span> <span id='attempts'>0</span></div>";
  html += "<div class='row'><span class='k'>Makes:</span> <span id='makes'>0</span></div>";
  html += "<div class='row'><span class='k'>Make %:</span> <span id='pct'>0</span></div>";

  html += "<hr>";
  html += "<div class='row'><span class='k'>Mode:</span> <span id='mode'>PUTT</span></div>";
  html += "<div class='row'><span class='k'>Distance:</span> <span id='dist'>0</span> ft</div>";

  html += "<div class='row'>";
  html += "<a href='/setmode?m=PUTT'>Mode PUTT</a> | <a href='/setmode?m=CHIP'>Mode CHIP</a>";
  html += "</div>";

  html += "<div class='row'>";
  html += "<a href='/setdist?ft=4'>4</a> <a href='/setdist?ft=6'>6</a> <a href='/setdist?ft=8'>8</a> ";
  html += "<a href='/setdist?ft=10'>10</a> <a href='/setdist?ft=12'>12</a>";
  html += "</div>";

  html += "<hr>";
  html += "<div class='row'><span class='k'>Prox:</span> <span id='prox'>...</span></div>";
  html += "<div class='row'><span class='k'>Baseline:</span> <span id='base'>...</span></div>";
  html += "<div class='row'><span class='k'>Delta:</span> <span id='delta'>...</span></div>";
  html += "<div class='row'><span class='k'>Threshold:</span> <span id='thr'>...</span></div>";
  html += "<div class='row'><span class='k'>Ball Present:</span> <span id='present'>...</span></div>";
  html += "<div class='row'><span class='k'>State:</span> <span id='state'>...</span></div>";

  html += "<hr>";
  html += "<div class='row'><a href='/start'>Start Session</a></div>";
  html += "<div class='row'><a href='/stop'>Stop (Save Local)</a></div>";
  html += "<div class='row'><a href='/stop_sync' style='font-weight:bold;'>Stop + Sync</a></div>";
  html += "<div class='row'><a href='/sync_pending'>Sync Pending</a></div>";

  html += "<hr>";
  html += "<div class='row'><a href='/calibrate'>Manual Calibrate (NO ball)</a></div>";
  html += "<div class='row'><a href='/reset' style='color:#b00;'>Reset Counters</a></div>";

  html += "<hr>";
  html += "<div class='row'><span class='k'>Sync state:</span> <span id='sync'>...</span></div>";

  html += "<script>";
  html += "async function tick(){"
          "try{"
            "const r=await fetch('/status',{cache:'no-store'});"
            "if(!r.ok) return;"
            "const s=await r.json();"

            // show banner while syncing
            "const syncing = (s.syncState != 0);"           // assuming 0 == SYNC_IDLE
            "document.getElementById('banner').style.display = syncing ? 'block' : 'none';"

            "document.getElementById('attempts').textContent=s.attempts;"
            "document.getElementById('makes').textContent=s.makes;"
            "document.getElementById('pct').textContent=s.pct+'%';"
            "document.getElementById('prox').textContent=s.prox;"
            "document.getElementById('base').textContent=s.baseline;"
            "document.getElementById('delta').textContent=s.delta;"
            "document.getElementById('thr').textContent=s.threshold;"
            "document.getElementById('present').textContent=s.present?'YES':'NO';"
            "document.getElementById('state').textContent=s.state;"
            "document.getElementById('mode').textContent=s.mode;"
            "document.getElementById('dist').textContent=s.distanceFt;"
            "document.getElementById('sync').textContent=s.syncState;"
            "document.getElementById('sess').textContent=(s.sessionActive?'ON':'OFF')+' (id '+s.sessionId+')';"
          "}catch(e){"
              "document.getElementById('banner').style.display = 'block';"
          "}"
        "}"
        "tick(); setInterval(tick, 250);";
  html += "</script>";

  html += "</body></html>";
  return html;
}


void handleRoot() {
  server.send(200, "text/html", page());
}


// ================= SYNC SCHEDULING (HTTP routes call this only) =================
bool scheduleSync(SyncRequestType req) {
  if (syncState != SYNC_IDLE) {
    Serial.println("[SYNC] Busy, cannot schedule");
    return false;
  }
  syncRequest = req;
  syncState = SYNC_PREP;
  syncStateMs = millis();
  syncOk = false;
  syncEpochNow = 0;

  Serial.print("[SYNC] Scheduled req=");
  Serial.println((int)req);
  return true;
}

void syncStateMachineTick() {
  if (syncState == SYNC_IDLE) return;

  switch (syncState) {
    case SYNC_PREP:
      // Give browser time to receive HTTP response and close TCP cleanly
      if (millis() - syncStateMs > 600) {
        syncState = SYNC_STOP_SERVER;
        syncStateMs = millis();
      }
      break;

    case SYNC_STOP_SERVER:
      Serial.println("[SYNC] Stopping web server");
      server.stop();
      delay(50);

      // Stop ESP-NOW before WiFi mode changes
      Serial.println("[SYNC] Deinit ESP-NOW");
      deinitEspNow();

      syncState = SYNC_WIFI_TO_STA;
      syncStateMs = millis();
      break;

    case SYNC_WIFI_TO_STA:
      Serial.println("[SYNC] Switching to STA mode");
      // Drop AP to allow STA to change channel without fighting
      WiFi.softAPdisconnect(true);
      delay(150);

      WiFi.mode(WIFI_STA);
      delay(150);

      syncState = SYNC_CONNECT_STA;
      syncStateMs = millis();
      break;

    case SYNC_CONNECT_STA: {
      bool ok = connectSta();
      if (!ok) {
        syncOk = false;
        syncState = SYNC_RETURN_TO_AP;
        syncStateMs = millis();
      } else {
        syncState = SYNC_NTP;
        syncStateMs = millis();
      }
      break;
    }

    case SYNC_NTP: {
      bool ok = ensureTimeNtp(syncEpochNow);
      if (!ok) {
        syncOk = false;
        syncState = SYNC_RETURN_TO_AP;
        syncStateMs = millis();
      } else {
        syncState = SYNC_POST;
        syncStateMs = millis();
      }
      break;
    }

    case SYNC_POST: {
      bool ok = false;

#if USE_LITTLEFS
      if (syncRequest == SYNC_STOP_AND_UPLOAD_CURRENT) {
        ok = pushCurrentSessionFromRam(syncEpochNow);
        if (ok) markSessionUploaded(sessionId);
      } else if (syncRequest == SYNC_UPLOAD_PENDING) {
        ok = pushPendingSessions(syncEpochNow);
      } else {
        ok = true;
      }
#else
      // No LittleFS: only supports posting current session from RAM
      if (syncRequest == SYNC_STOP_AND_UPLOAD_CURRENT) {
        // Build payload from RAM sessionRows
        if (sessionRows.empty()) {
          ok = true;
        } else {
          uint32_t nowMs = (uint32_t)millis();
          uint32_t startEpoch = syncEpochNow - (uint32_t)((nowMs - sessionStartMs) / 1000UL);

          String payload;
          payload.reserve(2048);
          payload += "{\"secret\":\"";
          payload += jsonEscape(sheetsSecret);
          payload += "\",\"rows\":[";

          for (size_t i = 0; i < sessionRows.size(); i++) {
            const AttemptRow& r = sessionRows[i];
            uint32_t attemptEpoch = startEpoch + (uint32_t)((r.attempt_ms - r.start_ms) / 1000UL);
            uint32_t makeEpoch = 0;
            if (r.make_ms > 0) makeEpoch = startEpoch + (uint32_t)((r.make_ms - r.start_ms) / 1000UL);

            payload += "[";
            payload += String(r.session_id); payload += ",";
            payload += String(startEpoch); payload += ",";
            payload += String(attemptEpoch); payload += ",";
            payload += String(r.distance_ft, 1); payload += ",";
            payload += "\""; payload += jsonEscape(r.mode); payload += "\",";
            payload += String(r.attempt_num); payload += ",";
            payload += "\""; payload += jsonEscape(r.result); payload += "\",";
            payload += String(makeEpoch);
            payload += "]";

            if (i + 1 < sessionRows.size()) payload += ",";
          }

          payload += "]}";
          ok = postToSheets(sheetsUrl, payload);
        }
      } else {
        ok = true;
      }
#endif

      syncOk = ok;

      syncState = SYNC_RETURN_TO_AP;
      syncStateMs = millis();
      break;
    }

    case SYNC_RETURN_TO_AP:
      Serial.println("[SYNC] Returning to AP + ESPNOW channel");
      disconnectSta();
      delay(150);

      // Rebuild AP+STA on fixed channel 6
      startApOnChannel();
      delay(200);

      // Re-init ESP-NOW receiver
      initEspNowReceiver();
      delay(100);

      syncState = SYNC_RESTART_SERVER;
      syncStateMs = millis();
      break;

    case SYNC_RESTART_SERVER:
      Serial.println("[SYNC] Restarting web server");
      server.begin();
      delay(50);

      syncState = SYNC_DONE;
      syncStateMs = millis();
      break;

    case SYNC_DONE:
      Serial.print("[SYNC] Done result=");
      Serial.println(syncOk ? "OK" : "FAIL");

      // Clear request and return idle
      syncRequest = SYNC_NONE;
      syncState = SYNC_IDLE;
      break;

    default:
      syncState = SYNC_IDLE;
      break;
  }
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

#if USE_LITTLEFS
  if (LittleFS.begin(true)) {
    Serial.println("[FS] LittleFS mounted");
    ensureSessionDir();
    loadConfig();
  } else {
    Serial.println("[FS] LittleFS mount failed");
  }
#endif

  // Sensor init
  if (!vcnl4200.begin()) {
    Serial.println("VCNL4200 not found! Check wiring.");
    while (1) delay(10);
  }
  Serial.println("VCNL4200 found!");
  applyProxConfig();

  // Auto baseline on boot
  runCalibration(false);

  // Start AP on fixed channel
  bool apOk = startApOnChannel();
  Serial.print("[WIFI] AP started: ");
  Serial.println(apOk ? "YES" : "NO");
  Serial.print("[WIFI] AP IP: ");
  Serial.println(WiFi.softAPIP());

  printChannel("[WIFI] Channel: ");
  printMacs();

  // ESP-NOW init
  if (!initEspNowReceiver()) {
    while (1) delay(10);
  }

  // Web routes
  server.on("/", handleRoot);

  server.on("/status", []() {
    uint16_t prox = readProxAvg();
    uint16_t threshold = baselineProx + thresholdDelta;
    bool present = prox > threshold;

    float pct = (attempts == 0) ? 0.0f : (100.0f * (float)makes / (float)attempts);

    String json = "{";
    json += "\"attempts\":" + String(attempts) + ",";
    json += "\"makes\":" + String(makes) + ",";
    json += "\"pct\":" + String(pct, 1) + ",";
    json += "\"prox\":" + String(prox) + ",";
    json += "\"baseline\":" + String(baselineProx) + ",";
    json += "\"delta\":" + String(thresholdDelta) + ",";
    json += "\"threshold\":" + String(threshold) + ",";
    json += "\"present\":" + String(present ? "true" : "false") + ",";
    json += "\"state\":\"" + stateName(state) + "\",";
    json += "\"sessionActive\":" + String(sessionActive ? "true" : "false") + ",";
    json += "\"sessionId\":" + String(sessionId) + ",";
    json += "\"mode\":\"" + shotMode + "\",";
    json += "\"distanceFt\":" + String(distanceFt, 1) + ",";
    json += "\"syncState\":" + String((int)syncState);
    json += "}";

    server.send(200, "application/json", json);
  });


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
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/setmode", []() {
    if (server.hasArg("m")) {
      String m = server.arg("m");
      m.toUpperCase();
      if (m == "PUTT" || m == "CHIP") shotMode = m;
    }
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/setdist", []() {
    if (server.hasArg("ft")) {
      float ft = server.arg("ft").toFloat();
      if (ft > 0.0f && ft < 100.0f) distanceFt = ft;
    }
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/setwifi", []() {
    if (server.hasArg("ssid")) staSsid = server.arg("ssid");
    if (server.hasArg("pass")) staPass = server.arg("pass");
#if USE_LITTLEFS
    saveConfig();
#endif
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/setsheets", []() {
    if (server.hasArg("url")) sheetsUrl = server.arg("url");
    if (server.hasArg("secret")) sheetsSecret = server.arg("secret");
#if USE_LITTLEFS
    saveConfig();
#endif
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/start", []() {
    if (!sessionActive) startSession();
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.on("/stop", []() {
    if (sessionActive) {
      stopSessionLocalOnly();
#if USE_LITTLEFS
      saveSessionToLittleFS(sessionId);
#endif
    }
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  // Correct architecture: schedule, do not run sync inside handler
  server.on("/stop_sync", []() {
    if (sessionActive) {
      stopSessionLocalOnly();
  #if USE_LITTLEFS
      saveSessionToLittleFS(sessionId);
  #endif
    }

    scheduleSync(SYNC_STOP_AND_UPLOAD_CURRENT);

    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });


  server.on("/sync_pending", []() {
  #if USE_LITTLEFS
    scheduleSync(SYNC_UPLOAD_PENDING);
  #endif
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.begin();
  Serial.println("Web server started");
  updateStatusLEDs();
}

// ================= LOOP =================
void loop() {
  // Run sync state machine first (it may stop/restart server)
  syncStateMachineTick();

  // Only handle clients when server is running
  if (syncState == SYNC_IDLE) {
    server.handleClient();
  }

  // ----- Button handling (debounced) -----
  static int lastReading = HIGH;
  static int stableState = HIGH;
  static unsigned long lastChangeMs = 0;

  int reading = digitalRead(CAL_BTN_PIN);
  unsigned long now = millis();

  if (reading != lastReading) {
    lastChangeMs = now;
    lastReading = reading;
  }

  if ((now - lastChangeMs) > DEBOUNCE_MS) {
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

      if (sessionActive) {
        attemptCounter++;

        AttemptRow r;
        r.session_id = sessionId;
        r.attempt_num = attemptCounter;
        r.start_ms = sessionStartMs;
        r.attempt_ms = (uint32_t)now;
        r.make_ms = 0;
        r.distance_ft = distanceFt;
        r.mode = shotMode;
        r.result = "MISS";

        sessionRows.push_back(r);
      }
    }
  }

  // ----- Debug -----
  if (debugSerial && (now - lastDebugMs) > DEBUG_PERIOD_MS) {
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
    Serial.print(sessionActive ? "ON" : "OFF");
    Serial.print(" syncState=");
    Serial.println((int)syncState);
  }
}
