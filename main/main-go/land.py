#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Misi Navigasi Segmen: Landing (Land)
Mengirim perintah LAND ke Pixhawk dan memantau proses pendaratan.
"""

import os
import sys
import time
import json
import threading
import math
from pymavlink import mavutil
from sensor_reader import ESP32Reader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', 'config', 'krti_config.json'))

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f: return json.load(f)
    print(f"❌ ERROR: Konfigurasi tidak ditemukan di {CONFIG_PATH}")
    sys.exit(1)

# Globals for telemetry
drone_telemetry = {'lat': 0.0, 'lon': 0.0, 'alt': 0.0, 'yaw': 0.0, 'roll': 0.0, 'pitch': 0.0, 'battery': -1}
drone_mode = "UNKNOWN"

def pixhawk_loop(master):
    global drone_telemetry, drone_mode
    while True:
        try:
            msg = master.recv_match(blocking=True, timeout=1.0)
            if not msg:
                continue
            mtype = msg.get_type()
            if mtype == 'GLOBAL_POSITION_INT':
                drone_telemetry['lat'] = msg.lat / 1e7
                drone_telemetry['lon'] = msg.lon / 1e7
                drone_telemetry['alt'] = msg.relative_alt / 1000.0
            elif mtype == 'ATTITUDE':
                drone_telemetry['roll'] = msg.roll
                drone_telemetry['pitch'] = msg.pitch
                yaw_deg = math.degrees(msg.yaw)
                if yaw_deg < 0: yaw_deg += 360
                drone_telemetry['yaw'] = yaw_deg
            elif mtype == 'SYS_STATUS':
                drone_telemetry['battery'] = msg.battery_remaining
            elif mtype == 'HEARTBEAT':
                if msg.type != mavutil.mavlink.MAV_TYPE_GCS:
                    drone_mode = mavutil.mode_string_v10(msg)
        except Exception:
            time.sleep(0.01)

def connect_pixhawk(port, baudrate):
    print(f"Menghubungkan ke Pixhawk di {port} ({baudrate})...")
    master = mavutil.mavlink_connection(port, baud=baudrate)
    master.wait_heartbeat()
    print("✅ Berhasil Terhubung ke Pixhawk!")
    master.mav.request_data_stream_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1
    )
    threading.Thread(target=pixhawk_loop, args=(master,), daemon=True).start()
    return master

def land_drone(master):
    if master is None: return
    print("⚠️ MENGIRIM PERINTAH LAND...")
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_NAV_LAND, 0,
        0, 0, 0, 0, 0, 0, 0
    )

LOG_FILE = os.path.join(BASE_DIR, 'land.log')
def log_msg(msg, level="INFO"):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, 'a') as f: f.write(line + '\n')
    except Exception: pass

def main():
    print("🚀 Memulai proses Landing...")
    config = load_config()
    port = config.get('pixhawk_port', '/dev/ttyACM0')
    baud = config.get('pixhawk_baudrate', 115200)
    
    esp_reader = None
    if config.get('use_obstacle_avoidance', True):
        esp_port = config.get('esp32_port', '/dev/ttyACM1')
        esp_baud = config.get('esp32_baudrate', 115200)
        try:
            esp_reader = ESP32Reader(port=esp_port, baudrate=esp_baud)
            esp_reader.start()
        except Exception as e:
            print(f"ESP32 Reader warning: {e}")

    master = connect_pixhawk(port, baud)

    log_msg("==== PROGRAM LAND DIMULAI ====", "ACTION")
    log_msg("Mengirim perintah LAND ke Pixhawk...", "ACTION")
    
    land_drone(master)
    
    start_time = time.time()
    last_log_time = 0

    try:
        while True:
            cur_alt = drone_telemetry['alt']
            mode = drone_mode
            
            if time.time() - last_log_time > 1.0:
                log_msg(f"Mode: {mode} | Alt: {cur_alt:.2f}m | Lat: {drone_telemetry['lat']:.6f} | Lon: {drone_telemetry['lon']:.6f}")
                last_log_time = time.time()

            master.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS,
                mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0
            )

            if mode == "LAND" or (cur_alt <= 0.15 and time.time() - start_time > 5.0) or (time.time() - start_time > 15.0):
                log_msg("✅ Pendaratan selesai atau perintah LAND telah berhasil diproses.", "ACTION")
                time.sleep(2.0)
                break

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n🛑 Landing dibatalkan oleh pengguna.")
    finally:
        if esp_reader:
            esp_reader.stop()

if __name__ == '__main__':
    main()
