#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Misi Navigasi Segmen: WP4 -> WP5 (Landing)
Berputar (Yaw) di tempat terlebih dahulu, maju menuju WP5, centering ArUco, dan Mendarat.
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
import web_dashboard_mission

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', 'config', 'krti_config.json'))

KP_XY = 0.0015
MAX_SPEED = 0.3
LOCK_TOLERANCE = 40
STABLE_DURATION = 3.0
TARGET_ID = 5  # Target ArUco ID untuk WP5
ARUCO_DICT_TYPE = cv2.aruco.DICT_7X7_50

STATE_INIT = 0
STATE_ROTATE_YAW = 1
STATE_GOTO_GPS = 2
STATE_CENTER_ARUCO = 3
STATE_LAND = 4
STATE_DONE = 5

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

def send_velocity(master, vx, vy, vz):
    if master is None: return
    master.mav.set_position_target_local_ned_send(
        0, master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_BODY_NED,
        0b0000111111000111, 0, 0, 0, vx, vy, vz, 0, 0, 0, 0, 0
    )

def goto_gps_position(master, lat, lon, alt):
    if master is None: return
    master.mav.set_position_target_global_int_send(
        0, master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        0b0000111111111000, int(lat * 1e7), int(lon * 1e7), alt,
        0, 0, 0, 0, 0, 0, 0, 0
    )

def rotate_to_yaw(master, target_yaw):
    if master is None: return
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_CONDITION_YAW, 0,
        target_yaw, 15, 1, 0, 0, 0, 0
    )

def land_drone(master):
    if master is None: return
    print("⚠️ MENGIRIM PERINTAH LAND...")
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_NAV_LAND, 0,
        0, 0, 0, 0, 0, 0, 0
    )

def get_shortest_yaw_diff(current_yaw, target_yaw):
    diff = (target_yaw - current_yaw) % 360
    if diff > 180: diff -= 360
    return abs(diff)

def main():
    config = load_config()
    port = config.get('pixhawk_port', '/dev/ttyACM0')
    baud = config.get('pixhawk_baudrate', 115200)
    cam_index = config.get('camera_index', 0)
    target_alt = config.get('target_altitude', 2.0)
    use_aruco = config.get('use_aruco_verification', True)
    
    team = config.get('team', 'Biru')
    wp_key = f'waypoints_{team}'
    wp_target = config.get(wp_key, {}).get('wp5', {})
    if not wp_target.get('lat'):
        print("❌ ERROR: Data WP5 belum dikalibrasi!")
        sys.exit(1)

    print(f"🎯 Target WP5: Lat {wp_target['lat']}, Lon {wp_target['lon']}, Yaw {wp_target['yaw']}")

    # Mulai Web Dashboard
    web_dashboard_mission.start_dashboard(team, port=5004)

    master = connect_pixhawk(port, baud)

    cap = None
    if use_aruco:
        if os.name == 'nt': cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
        else: cap = cv2.VideoCapture(cam_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT_TYPE)
    aruco_params = cv2.aruco.DetectorParameters()
    if hasattr(cv2.aruco, 'ArucoDetector'): detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)
    else: detector = None

    state = STATE_INIT
    stable_start_time = 0
    cur_lat, cur_lon, cur_yaw = None, None, None

    print("\n🚀 Menunggu mode GUIDED untuk memulai rotasi ke WP5.")
    
    try:
        while True:
            if drone_telemetry['lat'] != 0.0:
                cur_lat = drone_telemetry['lat']
                cur_lon = drone_telemetry['lon']
                cur_yaw = drone_telemetry['yaw']

            mode = drone_mode

            if use_aruco and cap is not None:
                ret, frame = cap.read()
                if not ret: continue
            else:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)

            h, w, _ = frame.shape
            cx_frame, cy_frame = w // 2, h // 2

            if detector: corners, ids, _ = detector.detectMarkers(frame)
            else: corners, ids, _ = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=aruco_params)

            display_frame = frame.copy()
            cv2.line(display_frame, (cx_frame - 20, cy_frame), (cx_frame + 20, cy_frame), (255, 0, 0), 2)
            cv2.line(display_frame, (cx_frame, cy_frame - 20), (cx_frame, cy_frame + 20), (255, 0, 0), 2)
            
            state_str = ""
            if mode != "GUIDED":
                state_str = "MENUNGGU MODE GUIDED"
                state = STATE_INIT
            else:
                if state == STATE_INIT:
                    print("✅ Mode GUIDED aktif. Memulai ROTASI YAW ke WP5.")
                    rotate_to_yaw(master, wp_target['yaw'])
                    state = STATE_ROTATE_YAW

                elif state == STATE_ROTATE_YAW:
                    state_str = "ROTASI YAW DI TEMPAT"
                    if cur_yaw is not None:
                        diff = get_shortest_yaw_diff(cur_yaw, wp_target['yaw'])
                        cv2.putText(display_frame, f"Yaw Diff: {diff:.1f} deg", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        if diff < 5.0:
                            print("✅ Rotasi selesai. Maju ke GPS WP5...")
                            state = STATE_GOTO_GPS
                        else:
                            rotate_to_yaw(master, wp_target['yaw'])

                elif state == STATE_GOTO_GPS:
                    state_str = "NAVIGASI MAJU (GPS) -> WP5"
                    if cur_lat and cur_lon:
                        dist = calculate_distance(cur_lat, cur_lon, wp_target['lat'], wp_target['lon'])
                        cv2.putText(display_frame, f"Dist WP5: {dist:.1f} m", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        if dist < 2.0:
                            if use_aruco:
                                print("✅ Mendekati WP5. Beralih ke pencarian ArUco!")
                                state = STATE_CENTER_ARUCO
                            else:
                                print("✅ Mendekati WP5. Verifikasi ArUco DINONAKTIFKAN. LANGSUNG LANDING...")
                                state = STATE_LAND
                        else:
                            goto_gps_position(master, wp_target['lat'], wp_target['lon'], target_alt)

                elif state == STATE_CENTER_ARUCO:
                    state_str = "VISUAL CENTERING WP5"
                    if ids is not None and TARGET_ID in ids:
                        idx = np.where(ids == TARGET_ID)[0][0]
                        points = corners[idx][0]
                        cx = int(np.mean(points[:, 0]))
                        cy = int(np.mean(points[:, 1]))
                        cv2.aruco.drawDetectedMarkers(display_frame, [corners[idx]], np.array([[TARGET_ID]]))
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
                                print("✅ ArUco WP5 Verified! MEMULAI PENDARATAN (LAND)...")
                                state = STATE_LAND
                                stable_start_time = 0
                        else: stable_start_time = 0
                    else:
                        send_velocity(master, 0, 0, 0)
                        cv2.putText(display_frame, f"MENCARI ARUCO ID {TARGET_ID}...", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                elif state == STATE_LAND:
                    state_str = "MENDARAT DI WP5"
                    land_drone(master)
                    state = STATE_DONE
                
                elif state == STATE_DONE:
                    state_str = "SEGMEN SELESAI (LANDED)"

            if cur_yaw is not None:
                cv2.putText(display_frame, f"Cur Yaw: {cur_yaw:.1f} / Target: {wp_target['yaw']:.1f}", (10, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(display_frame, f"MODE : {mode}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(display_frame, f"STATE: {state_str}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow("Navigasi WP4->WP5 (Landing)", display_frame)

            # Update dashboard
            web_dashboard_mission.update_dashboard(
                mode=mode, state_str=state_str,
                lat=drone_telemetry['lat'], lon=drone_telemetry['lon'], alt=drone_telemetry['alt'],
                yaw=drone_telemetry['yaw'], roll=drone_telemetry['roll'], pitch=drone_telemetry['pitch'],
                battery=drone_telemetry['battery']
            )

            master.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS,
                mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0
            )

            if cv2.waitKey(1) & 0xFF == ord('q'): break

    except KeyboardInterrupt: pass
    finally:
        try: send_velocity(master, 0, 0, 0)
        except: pass
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
