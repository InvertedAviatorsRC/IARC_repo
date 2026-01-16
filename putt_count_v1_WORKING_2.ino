#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include "Adafruit_VCNL4200.h"

// ESP-NOW
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_system.h>
#include <esp_mac.h>

// ================= WIFI / WEBUI =================
const char* AP_SSID = "PuttingTracker";
const char* AP_PASS = "puttputt1";
static const uint8_t ESPNOW_CHANNEL = 6;   // MUST match sender

WebServer server(80);

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

// ================= BUTTON DEBOUNCE (ROBUST) =================
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

// ================= ESP-NOW RECEIVE =================
void onEspNowRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  if (len != (int)sizeof(MakePacket)) return;

  MakePacket pkt;
  memcpy(&pkt, data, sizeof(pkt));

  if (pkt.event != 1) return;

  // De-dupe
  if (pkt.seq == 0 || pkt.seq == lastMakeSeq) return;
  lastMakeSeq = pkt.seq;

  makes++;

  Serial.print("[ESPNOW MAKE] makes=");
  Serial.print(makes);
  Serial.print(" seq=");
  Serial.println(pkt.seq);
}

// ================= WEB PAGE =================
String page(uint16_t prox) {
  uint16_t threshold = baselineProx + thresholdDelta;
  bool present = prox > threshold;

  float pct = (attempts == 0) ? 0.0f : (100.0f * (float)makes / (float)attempts);

  String html;
  html += "<html><head><meta name='viewport' content='width=device-width'>";
  html += "<meta http-equiv='refresh' content='1'></head><body>";
  html += "<h2>Total Putt Counter</h2>";

  html += "<p><b>Attempts:</b> " + String(attempts) + "</p>";
  html += "<p><b>Makes:</b> " + String(makes) + "</p>";
  html += "<p><b>Make %:</b> " + String(pct, 1) + "%</p>";

  html += "<hr>";
  html += "<p><b>Prox(avg):</b> " + String(prox) + "</p>";
  html += "<p><b>Baseline:</b> " + String(baselineProx) + (manualCalibrated ? " (MANUAL)" : " (AUTO)") + "</p>";
  html += "<p><b>Delta:</b> " + String(thresholdDelta) + "</p>";
  html += "<p><b>Threshold:</b> " + String(threshold) + "</p>";
  html += "<p><b>Ball Present:</b> " + String(present ? "YES" : "NO") + "</p>";
  html += "<p><b>State:</b> " + stateName(state) + "</p>";

  html += "<hr>";
  html += "<p><a href='/calibrate'>Manual Calibrate (NO ball)</a></p>";
  html += "<p><a href='/delta?d=100'>Delta 100</a> | <a href='/delta?d=200'>200</a> | <a href='/delta?d=300'>300</a> | <a href='/delta?d=500'>500</a></p>";
  html += "<p><a href='/reset' style='color:#b00;'>Reset Session</a></p>";

  html += "<hr>";
  html += "<p><b>WiFi Channel:</b> " + String(ESPNOW_CHANNEL) + "</p>";
  html += "<p><b>AP IP:</b> " + WiFi.softAPIP().toString() + "</p>";
  html += "<p><b>AP MAC:</b> " + WiFi.softAPmacAddress() + "</p>";

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

  // Auto baseline on boot
  runCalibration(false);

  // WiFi AP+STA, fixed channel
  WiFi.mode(WIFI_AP_STA);
  bool apOk = WiFi.softAP(AP_SSID, AP_PASS, ESPNOW_CHANNEL);
  Serial.print("AP started: ");
  Serial.println(apOk ? "YES" : "NO");
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());

  printChannel("Receiver WiFi channel: ");
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
    server.sendHeader("Location", "/");
    server.send(302, "text/plain", "");
  });

  server.begin();
  Serial.println("Web server started");
}

// ================= LOOP =================
void loop() {
  server.handleClient();

  // ----- Button handling (debounced, reliable) -----
  static int lastReading = HIGH;        // raw last reading
  static int stableState = HIGH;        // debounced stable state
  static unsigned long lastChangeMs = 0;

  int reading = digitalRead(CAL_BTN_PIN);

  if (reading != lastReading) {
    lastChangeMs = millis();
    lastReading = reading;
  }

  if ((millis() - lastChangeMs) > DEBOUNCE_MS) {
    if (reading != stableState) {
      stableState = reading;

      // press event = LOW (INPUT_PULLUP)
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
    Serial.println(stateName(state));
  }
}
