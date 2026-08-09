#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Misi Navigasi Segmen: HOME -> WP1
Berputar (Yaw) di tempat terlebih dahulu, lalu maju menuju WP1.
"""

import os
import sys
import cv2
import time
import json
import argparse
import numpy as np
import threading
import math
from pymavlink import mavutil
from sensor_reader import ESP32Reader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', 'config', 'krti_config.json'))

# Konfigurasi Control
KP_XY = 0.0015
MAX_SPEED = 0.3
LOCK_TOLERANCE = 40
STABLE_DURATION = 3.0
TARGET_ID = 1  # Target ArUco ID untuk WP1
ARUCO_DICT_TYPE = cv2.aruco.DICT_7X7_50

# States
STATE_INIT = 0
STATE_ROTATE_YAW = 1
STATE_WAIT_ALT = 2   # Tunggu ketinggian stabil setelah yaw selesai
STATE_GOTO_GPS = 3
STATE_CENTER_ARUCO = 4
STATE_DONE = 5

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
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

def send_velocity(master, vx, vy, vz):
    if master is None: return
    master.mav.set_position_target_local_ned_send(
        0, master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_BODY_NED,
        0b0000111111000111,
        0, 0, 0, vx, vy, vz, 0, 0, 0, 0, 0
    )

def goto_gps_position(master, lat, lon, alt, yaw_deg=None):
    """Kirim target posisi GPS. Kecepatan diatur via send_change_speed()."""
    if master is None: return
    
    if yaw_deg is None:
        type_mask = 0b0000111111111000  # Abaikan yaw
        yaw_rad = 0.0
    else:
        type_mask = 0b0000101111111000  # Gunakan yaw (bit 10=0)
        yaw_rad = 0.0 if yaw_deg is None else __import__('math').radians(yaw_deg)

    master.mav.set_position_target_global_int_send(
        0, master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        type_mask,
        int(lat * 1e7),
        int(lon * 1e7),
        alt,
        0, 0, 0, 0, 0, 0,
        yaw_rad, 0
    )

def send_change_speed(master, speed_ms):
    """Set kecepatan navigasi drone via MAV_CMD_DO_CHANGE_SPEED dan Parameter."""
    if master is None: return
    
    # 1. Cara standar MAVLink (berlaku untuk AUTO mode)
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED, 0,
        1,        # param1: 1 = ground speed
        speed_ms, # param2: kecepatan dalam m/s
        -1, 0, 0, 0, 0
    )
    
    # 2. Cara spesifik ArduCopter untuk GUIDED mode (WPNAV_SPEED dalam cm/s)
    master.mav.param_set_send(
        master.target_system, master.target_component,
        b'WPNAV_SPEED',
        speed_ms * 100.0,
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32
    )

def rotate_to_yaw(master, current_yaw, target_yaw):
    """Mengirim perintah berputar ke sudut yaw (absolute) dengan rute terpendek"""
    if master is None: return
    if current_yaw is None:
        direction = 1
    else:
        diff = (target_yaw - current_yaw) % 360
        direction = 1 if diff <= 180 else -1
    
    # MAV_CMD_CONDITION_YAW: param1: sudut, param2: kecepatan putar, param3: arah (-1 CCW, 1 CW), param4: relative=0/absolute=1
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_CONDITION_YAW, 0,
        target_yaw, 15, direction, 0, 0, 0, 0
    )

def get_shortest_yaw_diff(current_yaw, target_yaw):
    if current_yaw is None:
        return 999.0
    diff = (target_yaw - current_yaw) % 360
    if diff > 180: diff -= 360
    return abs(diff)

def get_bearing(lat1, lon1, lat2, lon2):
    dLon = math.radians(lon2 - lon1)
    y = math.sin(dLon) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dLon)
    bearing = math.atan2(y, x)
    return (math.degrees(bearing) + 360) % 360


def calculate_distance(lat1, lon1, lat2, lon2):
    """Menghitung jarak haversine antara dua koordinat GPS dalam meter."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# --- Setup File Logger ---
LOG_DIR = BASE_DIR
LOG_FILE = os.path.join(LOG_DIR, 'home-wp1.log')

def log_msg(msg, level="INFO"):
    """Menulis pesan ke konsol dan ke file log dengan timestamp."""
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
    except Exception:
        pass

def main():
    print("🚀 Sedang menjalankan misi menuju WP1...")
    config = load_config()
    port = config.get('pixhawk_port', '/dev/ttyACM0')
    baud = config.get('pixhawk_baudrate', 115200)
    cam_index = config.get('camera_index', 0)
    use_aruco = config.get('use_aruco_verification', True)
    use_obstacle_avoidance = config.get('use_obstacle_avoidance', True)
    
    team = config.get('team', 'Biru')
    wp_key = f'waypoints_{team}'
    wp_target = config.get(wp_key, {}).get('wp1', {})
    
    target_alt = wp_target.get('target_alt', config.get('target_altitude', 2.0))
    drone_speed = wp_target.get('speed', config.get('drone_speed', 1.5))
    global MAX_SPEED
    MAX_SPEED = wp_target.get('max_aruco_speed', config.get('max_aruco_speed', 0.3))
    if not wp_target.get('lat'):
        print("❌ ERROR: Data WP1 belum dikalibrasi!")
        sys.exit(1)

    print(f"🎯 Target WP1: Lat {wp_target['lat']}, Lon {wp_target['lon']}, Yaw {wp_target['yaw']}")

    # Mulai Web Dashboard

    # Inisialisasi ESP32 Sensor Reader
    esp_reader = None
    if config.get('use_obstacle_avoidance', True):
        esp_port = config.get('esp32_port', '/dev/ttyACM1')
        esp_baud = config.get('esp32_baudrate', 115200)
        esp_reader = ESP32Reader(port=esp_port, baudrate=esp_baud)
        esp_reader.start()

    master = connect_pixhawk(port, baud)

    cap = None
    if use_aruco:
        if os.name == 'nt': cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
        else: cap = cv2.VideoCapture(cam_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT_TYPE)
    aruco_params = cv2.aruco.DetectorParameters()
    has_new_api = hasattr(cv2.aruco, 'ArucoDetector')
    if has_new_api: detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    state = STATE_INIT
    stable_start_time = 0
    alt_stable_start = 0
    done_start_time = 0
    cur_lat, cur_lon, cur_yaw = None, None, None

    last_log_time = 0
    last_yaw_cmd_time = 0
    last_gps_cmd_time = 0

    log_msg(f"==== PROGRAM DIMULAI ==== Target WP1: Lat={wp_target['lat']}, Lon={wp_target['lon']}, Yaw={wp_target['yaw']}")
    log_msg("Menunggu mode GUIDED untuk memulai rotasi ke WP1.")
    
    try:
        while True:
            if drone_telemetry['lat'] != 0.0:
                cur_lat = drone_telemetry['lat']
                cur_lon = drone_telemetry['lon']
                cur_yaw = drone_telemetry['yaw']

            mode = drone_mode

            if use_aruco and cap is not None:
                ret, frame = cap.read()
                if not ret:
                    # Jangan skip state machine! Gunakan frame kosong jika kamera gagal baca
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
            else:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)

            h, w, _ = frame.shape
            cx_frame, cy_frame = w // 2, h // 2

            if has_new_api: corners, ids, _ = detector.detectMarkers(frame)
            else: corners, ids, _ = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=aruco_params)

            display_frame = frame.copy()
            cv2.line(display_frame, (cx_frame - 20, cy_frame), (cx_frame + 20, cy_frame), (255, 0, 0), 2)
            cv2.line(display_frame, (cx_frame, cy_frame - 20), (cx_frame, cy_frame + 20), (255, 0, 0), 2)
            
            state_str = ""

            if mode != "GUIDED":
                state_str = "MENUNGGU MODE GUIDED"
                state = STATE_INIT # Reset
                last_yaw_cmd_time = 0
                last_gps_cmd_time = 0
            else:
                if state == STATE_INIT:
                    if cur_yaw is None or cur_lat is None or cur_lon is None:
                        if time.time() - last_log_time > 1.0:
                            log_msg("Menunggu data telemetry Yaw/GPS dari Pixhawk...", "WAIT")
                            last_log_time = time.time()
                    else:
                        bearing = get_bearing(cur_lat, cur_lon, wp_target['lat'], wp_target['lon'])
                        log_msg(f"Mode GUIDED aktif. Naik ke {target_alt}m & Yaw ke {bearing:.1f} deg sambil maju.", "ACTION")
                        send_change_speed(master, drone_speed)
                        goto_gps_position(master, wp_target['lat'], wp_target['lon'], target_alt)
                        rotate_to_yaw(master, cur_yaw, bearing)
                        last_yaw_cmd_time = time.time()
                        last_gps_cmd_time = time.time()
                        state = STATE_GOTO_GPS

                elif state == STATE_GOTO_GPS:
                    front_dist_cm = esp_reader.get_distance("DEPAN", 999.0) if esp_reader else 999.0
                    
                    if use_obstacle_avoidance and front_dist_cm < 200.0:
                        state_str = "AWAS OBSTACLE! (HOVER)"
                        if time.time() - last_log_time > 0.9:
                            log_msg(f"BAHAYA! Objek di depan ({front_dist_cm:.1f} cm). Drone berhenti!", "WARNING")
                        send_velocity(master, 0, 0, 0)
                        last_gps_cmd_time = 0
                        cv2.putText(display_frame, f"OBSTACLE: {front_dist_cm} cm", (10, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    else:
                        state_str = "NAVIGASI MAJU (GPS) -> WP1"
                        if cur_lat and cur_lon:
                            dist = calculate_distance(cur_lat, cur_lon, wp_target['lat'], wp_target['lon'])
                            
                            arrival_dist = 2.0 if use_aruco else 0.05
                            yaw_diff = get_shortest_yaw_diff(cur_yaw, bearing) if cur_yaw else 999.0
                            if dist < arrival_dist and yaw_diff < 15.0:
                                if use_aruco:
                                    log_msg(f"Mendekati WP1 (Jarak: {dist:.1f}m). Beralih ke STATE_CENTER_ARUCO.", "ACTION")
                                    state = STATE_CENTER_ARUCO
                                else:
                                    log_msg(f"Tiba di WP1 (Jarak: {dist:.1f}m). ArUco NONAKTIF. SELESAI SEGMEN.", "ACTION")
                                    state = STATE_DONE
                            else:
                                if time.time() - last_gps_cmd_time > 0.5:
                                    log_msg(f"Mengirim GPS target. Jarak sisa: {dist:.1f}m | Kecepatan: {drone_speed}m/s", "NAV")
                                    goto_gps_position(master, wp_target['lat'], wp_target['lon'], target_alt, yaw_deg=bearing)
                                    last_gps_cmd_time = time.time()

                elif state == STATE_CENTER_ARUCO:
                    state_str = "VISUAL CENTERING WP1"
                    if ids is not None and len(ids) > 0:
                        idx = 0
                        detected_id = ids[idx][0]
                        points = corners[idx][0]
                        cx = int(np.mean(points[:, 0]))
                        cy = int(np.mean(points[:, 1]))
                        cv2.aruco.drawDetectedMarkers(display_frame, [corners[idx]], np.array([[detected_id]]))
                        cv2.line(display_frame, (cx_frame, cy_frame), (cx, cy), (0, 255, 255), 2)
                        
                        err_x = cx - cx_frame
                        err_y = cy - cy_frame
                        is_locked = abs(err_x) < LOCK_TOLERANCE and abs(err_y) < LOCK_TOLERANCE
                        
                        vx = np.clip(-1.0 * err_y * KP_XY, -MAX_SPEED, MAX_SPEED)
                        vy = np.clip(1.0 * err_x * KP_XY, -MAX_SPEED, MAX_SPEED)
                        send_velocity(master, vx, vy, 0.0)

                        if is_locked:
                            if stable_start_time == 0: stable_start_time = time.time()
                            elif time.time() - stable_start_time > STABLE_DURATION:
                                print("✅ ArUco WP1 Verified! SELESAI SEGMEN INI.")
                                state = STATE_DONE
                                stable_start_time = 0
                        else:
                            stable_start_time = 0
                    else:
                        # Jika ArUco tidak terdeteksi, tetap maju ke koordinat GPS target agar lebih dekat
                        if cur_lat and cur_lon:
                            dist = calculate_distance(cur_lat, cur_lon, wp_target['lat'], wp_target['lon'])
                            if dist > 0.4:
                                if time.time() - last_gps_cmd_time > 0.5:
                                    bearing = get_bearing(cur_lat, cur_lon, wp_target['lat'], wp_target['lon'])
                                    goto_gps_position(master, wp_target['lat'], wp_target['lon'], target_alt, yaw_deg=bearing)
                                    last_gps_cmd_time = time.time()
                            else:
                                send_velocity(master, 0, 0, 0)
                        else:
                            send_velocity(master, 0, 0, 0)
                        cv2.putText(display_frame, "MENCARI ARUCO...", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                elif state == STATE_DONE:
                    state_str = "SEGMEN SELESAI (HOVER)"
                    send_velocity(master, 0, 0, 0)
                    if done_start_time == 0:
                        done_start_time = time.time()
                    elif time.time() - done_start_time > 2.0:
                        log_msg("✅ Hover selesai. Mengakhiri script untuk lanjut ke segmen berikutnya.", "ACTION")
                        break

            if time.time() - last_log_time > 1.0:
                log_msg(f"Mode={mode} | State={state_str} | TgtYaw={wp_target['yaw']:.1f} | CurYaw={cur_yaw if cur_yaw else 0:.1f} | Lat={cur_lat if cur_lat else 0:.6f} | Lon={cur_lon if cur_lon else 0:.6f} | Alt={drone_telemetry['alt']:.1f}m")
                last_log_time = time.time()

            if cur_yaw is not None:
                cv2.putText(display_frame, f"Cur Yaw: {cur_yaw:.1f} / Target: {wp_target['yaw']:.1f}", (10, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(display_frame, f"MODE : {mode}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(display_frame, f"STATE: {state_str}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            # cv2.imshow("Navigasi WP1->WP1", display_frame) # Dinonaktifkan untuk Headless mode


            master.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS,
                mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0
            )

            # Minimal sleep agar loop tidak membebani CPU dan heartbeat terkirim stabil
            time.sleep(0.03)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     break

    except KeyboardInterrupt:
        pass
    finally:
        try: send_velocity(master, 0, 0, 0)
        except: pass
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        if esp_reader:
            esp_reader.stop()

if __name__ == '__main__':
    main()
