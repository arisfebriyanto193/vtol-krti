#include <HardwareSerial.h>
#include <AlfredoCRSF.h>

// Gunakan Serial2 pada ESP32 (Bisa disesuaikan pinnya)
// Secara default di kebanyakan board ESP32: RX2 = Pin 16, TX2 = Pin 17
#define RX_PIN 16
#define TX_PIN 17

HardwareSerial crsfSerial(2);
AlfredoCRSF crsf;

void setup() {
  // Serial Monitor untuk dilihat di PC
  Serial.begin(115200); 
  
  // Receiver ExpressLRS (CRSF) secara default berkomunikasi di baudrate 420000
  crsfSerial.begin(420000, SERIAL_8N1, RX_PIN, TX_PIN);
  
  // Inisialisasi pembacaan CRSF
  crsf.begin(crsfSerial);
  
  Serial.println("=========================================");
  Serial.println("ESP32 ELRS (CRSF) Reader Started...");
  Serial.println("Menunggu data dari Remote...");
  Serial.println("=========================================");
}

void loop() {
  // Fungsi ini wajib dipanggil terus menerus untuk membaca aliran data
  crsf.update();
  
  // Cetak data setiap 200 milidetik agar Serial Monitor tidak nge-lag (flood)
  static unsigned long lastPrint = 0;
  if (millis() - lastPrint > 200) {
    lastPrint = millis();
    
    // Mengambil nilai Channel (1-16)
    // Nilai standar CRSF berkisar antara 988 hingga 2012 (tengah = 1500)
    int ch1 = crsf.getChannel(1); // Biasanya Roll / Aileron
    int ch2 = crsf.getChannel(2); // Biasanya Pitch / Elevator
    int ch3 = crsf.getChannel(3); // Biasanya Throttle
    int ch4 = crsf.getChannel(4); // Biasanya Yaw / Rudder
    int ch5 = crsf.getChannel(5); // Biasanya AUX 1 (Arming)
    
    // Cek apakah ada koneksi ke remote
    // Jika tidak ada data, AlfredoCRSF akan me-return nilai 0
    if (ch1 == 0) {
      Serial.println("[STATUS] NO SIGNAL / Receiver belum Bind!");
    } else {
      Serial.print("CH1: "); Serial.print(ch1);
      Serial.print(" | CH2: "); Serial.print(ch2);
      Serial.print(" | CH3: "); Serial.print(ch3);
      Serial.print(" | CH4: "); Serial.print(ch4);
      Serial.print(" | AUX1 (Arm): "); Serial.println(ch5);
    }
  }
}
