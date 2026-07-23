// ===============================
// ESP32-S3 + 6 Sensor HC-SR04
// ===============================

// Sensor 1
#define TRIG1 1
#define ECHO1 2

// Sensor 2
#define TRIG2 13
#define ECHO2 12

// Sensor 3
#define TRIG3 11
#define ECHO3 10

// Sensor 4
#define TRIG4 8
#define ECHO4 9

// Sensor 5
#define TRIG5 6
#define ECHO5 7

// Sensor 6
#define TRIG6 4
#define ECHO6 5

float bacaJarak(int trigPin, int echoPin) {
  long durasi;

  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  durasi = pulseIn(echoPin, HIGH, 30000); // timeout 30 ms

  if (durasi == 0) {
    return -1; // Tidak ada pantulan
  }

  return durasi * 0.0343 / 2.0;
}

void setup() {
  Serial.begin(115200);

  pinMode(TRIG1, OUTPUT);
  pinMode(ECHO1, INPUT);

  pinMode(TRIG2, OUTPUT);
  pinMode(ECHO2, INPUT);

  pinMode(TRIG3, OUTPUT);
  pinMode(ECHO3, INPUT);

  pinMode(TRIG4, OUTPUT);
  pinMode(ECHO4, INPUT);

  pinMode(TRIG5, OUTPUT);
  pinMode(ECHO5, INPUT);

  pinMode(TRIG6, OUTPUT);
  pinMode(ECHO6, INPUT);

  digitalWrite(TRIG1, LOW);
  digitalWrite(TRIG2, LOW);
  digitalWrite(TRIG3, LOW);
  digitalWrite(TRIG4, LOW);
  digitalWrite(TRIG5, LOW);
  digitalWrite(TRIG6, LOW);

  Serial.println("=== 6 Sensor Ultrasonik HC-SR04 ===");
}

void loop() {

  Serial.print("KIRI: ");
  Serial.print(bacaJarak(TRIG1, ECHO1));
  Serial.print(" cm\t");

  delay(50);

  Serial.print("ATAS: ");
  Serial.print(bacaJarak(TRIG2, ECHO2));
  Serial.print(" cm\t");

  delay(50);

  Serial.print("BAWAH: ");
  Serial.print(bacaJarak(TRIG3, ECHO3));
  Serial.print(" cm\t");

  delay(50);

  Serial.print("DEPAN: ");
  Serial.print(bacaJarak(TRIG4, ECHO4));
  Serial.print(" cm\t");

  delay(50);

  Serial.print("KANAN: ");
  Serial.print(bacaJarak(TRIG5, ECHO5));
  Serial.print(" cm\t");

  delay(50);

  Serial.print("BELAKANG: ");
  Serial.print(bacaJarak(TRIG6, ECHO6));
  Serial.println(" cm");

  Serial.println("--------------------------------");

  delay(500);
}