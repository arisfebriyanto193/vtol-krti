import serial
import json
import threading
import time

class ESP32Reader:
    def __init__(self, port, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.latest_data = {
            "sensors": {},
            "problems": [],
            "ts": 0
        }
        self.running = False
        self.thread = None

    def start(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=2)
            time.sleep(2) # Stabilisasi
            self.ser.reset_input_buffer()
            print(f"[ESP32] Terhubung ke {self.port}")
            self.running = True
            self.thread = threading.Thread(target=self._read_loop, daemon=True)
            self.thread.start()
        except serial.SerialException as e:
            print(f"[ESP32 ERROR] Gagal membuka port {self.port}: {e}")

    def _read_loop(self):
        while self.running and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    try:
                        data = json.loads(line)
                        self.latest_data = data
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                print(f"[ESP32 READ ERROR] {e}")
                time.sleep(1)

    def get_latest_data(self):
        return self.latest_data

    def get_bottom_distance(self):
        """Mendapatkan jarak sensor bawah (untuk kalibrasi)"""
        sensors = self.latest_data.get("sensors", {})
        bottom_sensor = sensors.get("BAWAH", {})
        dist = bottom_sensor.get("distance_cm")
        return dist if dist is not None else 0.0

    def stop(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
