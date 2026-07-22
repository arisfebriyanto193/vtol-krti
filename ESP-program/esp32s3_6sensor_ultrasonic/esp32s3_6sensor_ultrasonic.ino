/*
 * ESP32-S3 - 6x HC-SR04 Ultrasonic Sensor Reader
 * Dual-Core + Mutex Architecture
 * ------------------------------------------------
 * Core 0 (Task: SensorReadTask)  -> membaca 6 sensor bergantian, non-blocking timing
 * Core 1 (Task: CommTask)        -> kirim data via Serial JSON + deteksi sensor error
 *
 * Penamaan sensor:
 *   0 = DEPAN
 *   1 = BELAKANG
 *   2 = KANAN
 *   3 = KIRI
 *   4 = ATAS
 *   5 = BAWAH
 *
 * Wiring tiap sensor: VCC->5V, GND->GND, TRIG->pin, ECHO->pin (pakai voltage divider
 * 1k/2k dari ECHO ke GPIO karena ECHO HC-SR04 output 5V, GPIO ESP32-S3 max 3.3V!)
 */

#include <Arduino.h>
#include <ArduinoJson.h>   // install via Library Manager: "ArduinoJson" by Benoit Blanchon

// ================= KONFIGURASI PIN =================
// Sesuaikan dengan wiring fisik kamu
#define NUM_SENSORS 6

struct SensorPin {
  const char* name;
  uint8_t trigPin;
  uint8_t echoPin;
};

SensorPin sensorPins[NUM_SENSORS] = {
  {"DEPAN",    8,  9},
  {"BELAKANG", 5,  4},
  {"KANAN",    7, 6},
  {"KIRI",     1, 2},
  {"ATAS",     38,  39},
  {"BAWAH",    42, 41}
};

// ================= KONFIGURASI TIMING =================
#define SOUND_SPEED_CM_US     0.0343f     // kecepatan suara cm/us
#define MAX_DISTANCE_CM        400.0f     // batas maksimum jarak valid HC-SR04
#define MIN_DISTANCE_CM        2.0f       // batas minimum jarak valid HC-SR04
#define TRIGGER_PULSE_US       10         // durasi pulsa trigger (standar HC-SR04: 10us)
#define ECHO_TIMEOUT_US        25000UL    // timeout echo (~25ms => jarak > 400cm dianggap timeout)
#define SENSOR_STALE_MS        1000UL     // jika sensor tidak update > 1 detik -> dianggap ERROR
#define READ_INTERVAL_MS       60UL       // jeda antar siklus baca semua sensor (ms)
#define SEND_INTERVAL_MS       200UL      // interval kirim data ke Python (ms)

// ================= STRUKTUR DATA SENSOR (SHARED) =================
struct SensorData {
  float distance_cm;       // hasil terakhir (NAN jika invalid)
  unsigned long lastUpdate; // millis() saat terakhir sukses dibaca
  unsigned long lastAttempt; // millis() saat terakhir dicoba baca (sukses/gagal)
  bool valid;               // apakah reading terakhir valid
  uint32_t errorCount;      // jumlah error berturut-turut
  uint32_t totalReads;      // total percobaan baca
  uint32_t totalErrors;     // total error sepanjang runtime
};

volatile SensorData g_sensorData[NUM_SENSORS];

// ================= MUTEX =================
SemaphoreHandle_t xSensorMutex;

// ================= TASK HANDLES =================
TaskHandle_t TaskSensorRead;
TaskHandle_t TaskComm;

// ============================================================
// FUNGSI: baca 1 sensor HC-SR04 (blocking pulseIn, tapi cepat)
// ============================================================
float readUltrasonicSensor(uint8_t trigPin, uint8_t echoPin) {
  // pastikan trig low dulu (stabilisasi)
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  // kirim pulsa trigger 10us
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(TRIGGER_PULSE_US);
  digitalWrite(trigPin, LOW);

  // ukur lebar pulsa echo (dengan timeout, supaya tidak hang jika sensor putus/rusak)
  unsigned long duration = pulseIn(echoPin, HIGH, ECHO_TIMEOUT_US);

  if (duration == 0) {
    // timeout -> tidak ada echo diterima (sensor error / tidak terhubung / jarak > 400cm)
    return NAN;
  }

  float distance = (duration * SOUND_SPEED_CM_US) / 2.0f;

  // validasi range fisik HC-SR04
  if (distance < MIN_DISTANCE_CM || distance > MAX_DISTANCE_CM) {
    return NAN;
  }

  return distance;
}

// ============================================================
// TASK 1 (CORE 0): Membaca 6 sensor secara bergantian, non-blocking
// ============================================================
void SensorReadTaskCode(void* parameter) {
  Serial.println("[Core 0] SensorReadTask started");

  // inisialisasi pin
  for (int i = 0; i < NUM_SENSORS; i++) {
    pinMode(sensorPins[i].trigPin, OUTPUT);
    pinMode(sensorPins[i].echoPin, INPUT);
    digitalWrite(sensorPins[i].trigPin, LOW);
  }
  delay(50); // stabilisasi awal sensor

  uint8_t currentSensor = 0;

  for (;;) {
    unsigned long attemptTime = millis();

    // baca 1 sensor per iterasi (bergiliran round-robin)
    // ini membuat pembacaan lebih stabil/cepat karena tidak menunggu
    // total waktu 6 sensor sekaligus sebelum lanjut ke logic lain
    float dist = readUltrasonicSensor(sensorPins[currentSensor].trigPin,
                                       sensorPins[currentSensor].echoPin);

    // --- kunci mutex sebelum update shared data ---
    if (xSemaphoreTake(xSensorMutex, pdMS_TO_TICKS(50)) == pdTRUE) {

      g_sensorData[currentSensor].lastAttempt = attemptTime;
      g_sensorData[currentSensor].totalReads++;

      if (!isnan(dist)) {
        g_sensorData[currentSensor].distance_cm = dist;
        g_sensorData[currentSensor].lastUpdate = attemptTime;
        g_sensorData[currentSensor].valid = true;
        g_sensorData[currentSensor].errorCount = 0; // reset error berturut-turut
      } else {
        g_sensorData[currentSensor].valid = false;
        g_sensorData[currentSensor].errorCount++;
        g_sensorData[currentSensor].totalErrors++;
        // distance_cm TIDAK diupdate (biarkan nilai lama / NAN), tapi valid=false
      }

      xSemaphoreGive(xSensorMutex); // --- lepas mutex ---
    }

    // pindah ke sensor berikutnya
    currentSensor = (currentSensor + 1) % NUM_SENSORS;

    // jeda kecil antar sensor untuk menghindari crosstalk gelombang ultrasonik
    // (echo sensor A bisa "nyasar" ke trigger sensor B kalau terlalu berdekatan jaraknya)
    vTaskDelay(pdMS_TO_TICKS(READ_INTERVAL_MS / NUM_SENSORS));
  }
}

// ============================================================
// TASK 2 (CORE 1): Kirim data JSON + deteksi sensor bermasalah
// ============================================================
void CommTaskCode(void* parameter) {
  Serial.println("[Core 1] CommTask started");

  for (;;) {
    unsigned long now = millis();

    // buat JSON document
    StaticJsonDocument<768> doc;
    doc["ts"] = now;

    JsonObject sensors = doc.createNestedObject("sensors");
    JsonArray problems = doc.createNestedArray("problems"); // list sensor bermasalah

    if (xSemaphoreTake(xSensorMutex, pdMS_TO_TICKS(50)) == pdTRUE) {

      for (int i = 0; i < NUM_SENSORS; i++) {
        SensorData local = const_cast<SensorData&>(g_sensorData[i]); // copy lokal supaya cepat lepas mutex

        JsonObject s = sensors.createNestedObject(sensorPins[i].name);

        // Tentukan status sensor
        bool isStale = (local.lastUpdate == 0) ||
                       ((now - local.lastUpdate) > SENSOR_STALE_MS);
        bool isProblem = isStale || (local.errorCount >= 5);

        if (!isProblem && local.valid) {
          s["distance_cm"] = round(local.distance_cm * 100) / 100.0;
          s["status"] = "OK";
        } else {
          s["distance_cm"] = (const char*)nullptr; // null di JSON
          s["status"] = isStale ? "NO_ECHO/TIMEOUT" : "UNSTABLE";

          JsonObject p = problems.createNestedObject();
          p["sensor"] = sensorPins[i].name;
          p["reason"] = isStale ? "Tidak ada respon echo (kemungkinan putus/rusak)"
                                 : "Error beruntun terdeteksi";
          p["consecutive_errors"] = local.errorCount;
          p["last_update_ms_ago"] = (local.lastUpdate == 0) ? -1 : (long)(now - local.lastUpdate);
        }

        s["total_reads"] = local.totalReads;
        s["total_errors"] = local.totalErrors;
      }

      xSemaphoreGive(xSensorMutex);
    }

    // kirim ke Serial (dibaca Python via pyserial)
    serializeJson(doc, Serial);
    Serial.println(); // newline sebagai delimiter antar-JSON

    vTaskDelay(pdMS_TO_TICKS(SEND_INTERVAL_MS));
  }
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== ESP32-S3 6x HC-SR04 Dual-Core Ultrasonic Reader ===");

  // inisialisasi struct data sensor
  for (int i = 0; i < NUM_SENSORS; i++) {
    g_sensorData[i].distance_cm = NAN;
    g_sensorData[i].lastUpdate = 0;
    g_sensorData[i].lastAttempt = 0;
    g_sensorData[i].valid = false;
    g_sensorData[i].errorCount = 0;
    g_sensorData[i].totalReads = 0;
    g_sensorData[i].totalErrors = 0;
  }

  // buat mutex
  xSensorMutex = xSemaphoreCreateMutex();
  if (xSensorMutex == NULL) {
    Serial.println("FATAL: Gagal membuat mutex!");
    while (1) delay(1000);
  }

  // Task pembacaan sensor -> pinned ke Core 0
  xTaskCreatePinnedToCore(
    SensorReadTaskCode,
    "SensorReadTask",
    4096,
    NULL,
    2,          // priority lebih tinggi karena timing-sensitive
    &TaskSensorRead,
    0           // Core 0
  );

  // Task komunikasi -> pinned ke Core 1
  xTaskCreatePinnedToCore(
    CommTaskCode,
    "CommTask",
    4096,
    NULL,
    1,
    &TaskComm,
    1           // Core 1
  );

  Serial.println("Kedua task berjalan di Core 0 dan Core 1.\n");
}

void loop() {
  // tidak dipakai, semua logic ada di FreeRTOS task
  vTaskDelete(NULL);
}
