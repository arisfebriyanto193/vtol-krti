#!/usr/bin/env python3
"""
Python Serial Receiver - ESP32-S3 6x HC-SR04 Ultrasonic
---------------------------------------------------------
Membaca stream JSON dari ESP32-S3 via Serial (USB),
menampilkan data 6 sensor (depan, belakang, kanan, kiri, atas, bawah),
dan membuat report otomatis jika ada sensor bermasalah/tidak terbaca.

Install dependency:
    pip install pyserial --break-system-packages

Jalankan:
    python3 receiver_6sensor.py --port /dev/ttyUSB0
    (Windows: --port COM5)
"""

import serial
import json
import time
import argparse
import sys
import re
from datetime import datetime
from collections import defaultdict

# Urutan penamaan sensor sesuai request
SENSOR_NAMES = ["DEPAN", "BELAKANG", "KANAN", "KIRI", "ATAS", "BAWAH"]


class SensorMonitor:
    def __init__(self, port, baudrate=115200, log_file=None):
        self.port = port
        self.baudrate = baudrate
        self.log_file = log_file
        self.ser = None

        # statistik untuk report
        self.problem_history = defaultdict(int)   # hitung berapa kali tiap sensor bermasalah
        self.last_good_reading = {}                # simpan reading valid terakhir per sensor
        self.session_start = datetime.now()
        self.total_packets = 0
        self.malformed_packets = 0

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=2)
            print(f"[OK] Terhubung ke {self.port} @ {self.baudrate} baud")
            time.sleep(2)  # tunggu ESP32 reset setelah buka serial port
            self.ser.reset_input_buffer()
        except serial.SerialException as e:
            print(f"[ERROR] Gagal membuka port {self.port}: {e}")
            print("Cek: kabel USB, port yang benar, atau port sedang dipakai program lain.")
            sys.exit(1)

    def read_loop(self):
        print("Mulai membaca data sensor... (Ctrl+C untuk berhenti)\n")
        print(f"{'TIMESTAMP':<12} | " + " | ".join(f"{n:<10}" for n in SENSOR_NAMES) + " | STATUS")
        print("-" * 100)

        try:
            while True:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if not line or line.startswith("-") or line.startswith("="):
                    continue

                self.total_packets += 1

                matches = re.findall(r'([A-Z]+):\s*([-\d.]+)\s*cm', line)
                if matches:
                    sensors_data = {}
                    problems = []
                    for key, val_str in matches:
                        try:
                            val = float(val_str)
                            status = "OK" if val >= 0 else "ERROR"
                            sensors_data[key] = {"distance_cm": val, "status": status}
                            if val < 0:
                                problems.append({
                                    "sensor": key, 
                                    "reason": "Tidak ada pantulan (-1)", 
                                    "consecutive_errors": 1, 
                                    "last_update_ms_ago": 0
                                })
                        except ValueError:
                            pass
                    
                    if sensors_data:
                        data = {
                            "sensors": sensors_data,
                            "problems": problems,
                            "ts": time.time()
                        }
                        self._process_packet(data)
                    else:
                        self.malformed_packets += 1
                else:
                    self.malformed_packets += 1

        except KeyboardInterrupt:
            print("\n\nDihentikan oleh user.")
        finally:
            self.print_final_report()
            if self.ser and self.ser.is_open:
                self.ser.close()

    def _process_packet(self, data):
        sensors = data.get("sensors", {})
        problems = data.get("problems", [])
        ts = data.get("ts", 0)

        # format baris tampilan realtime
        row_values = []
        for name in SENSOR_NAMES:
            s = sensors.get(name, {})
            dist = s.get("distance_cm")
            status = s.get("status", "?")

            if dist is not None:
                self.last_good_reading[name] = dist
                row_values.append(f"{dist:>6.1f}cm")
            else:
                row_values.append(f"{'--':>8}")

            if status != "OK":
                self.problem_history[name] += 1

        status_str = "OK" if not problems else f"WARNING ({len(problems)} sensor bermasalah)"
        time_str = datetime.now().strftime("%H:%M:%S")

        print(f"{time_str:<12} | " + " | ".join(f"{v:<10}" for v in row_values) + f" | {status_str}")

        # tampilkan detail masalah begitu terdeteksi
        if problems:
            for p in problems:
                print(f"    -> [!] Sensor '{p['sensor']}': {p['reason']} "
                      f"(error beruntun: {p['consecutive_errors']}, "
                      f"update terakhir: {p['last_update_ms_ago']}ms lalu)")

        # log ke file jika diminta
        if self.log_file:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(data) + "\n")

    def print_final_report(self):
        """Report akhir: sensor mana yang paling sering bermasalah selama sesi berjalan."""
        duration = (datetime.now() - self.session_start).total_seconds()

        print("\n" + "=" * 60)
        print("REPORT SESI PEMBACAAN SENSOR")
        print("=" * 60)
        print(f"Durasi sesi        : {duration:.1f} detik")
        print(f"Total paket diterima: {self.total_packets}")
        print(f"Paket rusak/invalid : {self.malformed_packets}")
        print()

        any_problem = False
        for name in SENSOR_NAMES:
            count = self.problem_history.get(name, 0)
            last_val = self.last_good_reading.get(name)
            last_val_str = f"{last_val:.1f} cm" if last_val is not None else "TIDAK PERNAH TERBACA"

            if count > 0:
                any_problem = True
                print(f"  [BERMASALAH] {name:<10} -> {count}x error terdeteksi | "
                      f"reading valid terakhir: {last_val_str}")
            else:
                print(f"  [NORMAL]     {name:<10} -> tidak ada masalah | "
                      f"reading terakhir: {last_val_str}")

        print()
        if any_problem:
            print(">> KESIMPULAN: Ada sensor yang perlu dicek kabel/koneksinya (lihat daftar di atas).")
        else:
            print(">> KESIMPULAN: Semua 6 sensor berfungsi normal selama sesi ini.")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Receiver data 6 sensor HC-SR04 dari ESP32-S3")
    parser.add_argument("--port", required=True, help="Serial port, contoh: /dev/ttyUSB0 atau COM5")
    parser.add_argument("--baud", type=int, default=115200, help="Baudrate (default: 115200)")
    parser.add_argument("--log", default=None, help="Path file log JSON (opsional), contoh: log.jsonl")
    args = parser.parse_args()

    monitor = SensorMonitor(args.port, args.baud, args.log)
    monitor.connect()
    monitor.read_loop()


if __name__ == "__main__":
    main()  