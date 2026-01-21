#include <Wire.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Adafruit_VL6180X.h>

Adafruit_VL6180X vl = Adafruit_VL6180X();

// ===== ESPNOW SETTINGS =====
static const uint8_t ESPNOW_CHANNEL = 6; // MUST match receiver AP channel
uint8_t receiverMac[] = {0xF4,0x65,0x0B,0xC2,0x4E,0x7D};

typedef struct __attribute__((packed)) {
  uint32_t seq;
  uint8_t  event; // 1 = MAKE
} MakePacket;

uint32_t makeSeq = 0;

// ===== DETECTION TUNING =====
int baselineMm = 0;
int triggerDeltaMm = 12;          // tune this
unsigned long cooldownMs = 2500;  // tune this

const int SAMPLE_N = 5;
int consecutiveHitsNeeded = 2;

unsigned long lastMakeMs = 0;

int readRangeAvgMm(uint8_t* outStatus = nullptr) {
  uint32_t sum = 0;
  uint8_t lastStatus = 0;

  for (int i = 0; i < SAMPLE_N; i++) {
    uint8_t r = vl.readRange();
    lastStatus = vl.readRangeStatus();
    sum += r;
    delay(5);
  }
  if (outStatus) *outStatus = lastStatus;
  return (int)(sum / SAMPLE_N);
}

int measureBaselineMm() {
  uint32_t sum = 0;
  const int N = 30;
  for (int i = 0; i < N; i++) {
    sum += vl.readRange();
    delay(20);
  }
  return (int)(sum / N);
}

void setupEspNowSender() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true, true);

  // Force STA channel so ESP-NOW matches the receiver AP channel
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  esp_wifi_set_promiscuous(false);

  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW init failed!");
    while (1) delay(10);
  }

  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, receiverMac, 6);
  peer.channel = ESPNOW_CHANNEL;
  peer.encrypt = false;

  if (esp_now_add_peer(&peer) != ESP_OK) {
    Serial.println("Failed to add ESP-NOW peer!");
    while (1) delay(10);
  }

  Serial.println("ESP-NOW sender ready");
}

void sendMakeEvent() {
  MakePacket pkt;
  pkt.seq = ++makeSeq;
  pkt.event = 1;

  esp_err_t result = esp_now_send(receiverMac, (uint8_t*)&pkt, sizeof(pkt));

  Serial.print("[SEND MAKE] seq=");
  Serial.print(pkt.seq);
  Serial.print(" result=");
  Serial.println(result == ESP_OK ? "OK" : "FAIL");
}

void setup() {
  Serial.begin(115200);
  delay(300);

  Wire.begin(21, 22);

  Serial.println("Made-Putt Module v1 (VL6180X + ESP-NOW)");

  if (!vl.begin()) {
    Serial.println("Failed to find VL6180X, check wiring!");
    while (1) delay(10);
  }
  Serial.println("VL6180X found!");

  setupEspNowSender();

  baselineMm = measureBaselineMm();
  Serial.print("[BASELINE] baselineMm=");
  Serial.println(baselineMm);

  Serial.println("Roll a ball through and watch readings. Tune triggerDeltaMm if needed.");
}

void loop() {
  unsigned long now = millis();

  uint8_t status = 0;
  int r = readRangeAvgMm(&status);

  int triggerMm = baselineMm - triggerDeltaMm;
  bool inCooldown = (now - lastMakeMs) < cooldownMs;

  static int hitCount = 0;

  bool ballPresent = (!inCooldown) && (status == 0) && (r <= triggerMm);

  if (ballPresent) hitCount++;
  else hitCount = 0;

  if (hitCount >= consecutiveHitsNeeded) {
    lastMakeMs = now;
    hitCount = 0;

    Serial.print("[MAKE DETECTED] rangeAvg=");
    Serial.print(r);
    Serial.print(" baseline=");
    Serial.print(baselineMm);
    Serial.print(" trigger=");
    Serial.println(triggerMm);

    sendMakeEvent();
  }

  static unsigned long lastPrint = 0;
  if (now - lastPrint > 250) {
    lastPrint = now;
    Serial.print("rangeAvg=");
    Serial.print(r);
    Serial.print(" status=");
    Serial.print(status);
    Serial.print(" baseline=");
    Serial.print(baselineMm);
    Serial.print(" trigger=");
    Serial.print(triggerMm);
    Serial.print(" cooldown=");
    Serial.println(inCooldown ? "1" : "0");
  }
}
