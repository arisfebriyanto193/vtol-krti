#!/usr/bin/env python3
"""
Misi 2 KRTI VTOL (Versi Web): Navigasi dari WP1 ke WP2, Deteksi Box Merah, dan Drop Payload (Servo)
"""

import os
import sys
import cv2
import time
import argparse
import numpy as np
import threading
from pymavlink import mavutil
from flask import Flask, Response

# Menambahkan path folder 'main' ke sys.path agar bisa membaca folder 'config'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.main import PIXHAWK_PORT, PIXHAWK_BAUD, CAMERA_INDEX

# ================= KONFIGURASI =================
TARGET_ALTITUDE = 1.5     # Target ketinggian (meter)
KP_XY = 0.005             # Proportional gain sumbu X dan Y
KP_Z = 0.5                # Proportional gain ketinggian
MAX_SPEED = 0.5           # Kecepatan maksimal drone (m/s)
FORWARD_SPEED = 0.5       # Kecepatan maju menuju WP2 (m/s)

# Konfigurasi Servo (Drop Payload)
SERVO_PIN = 9             # Pin servo pada Pixhawk (AUX 1 biasanya pin 9)
SERVO_PWM_OPEN = 1900     # Nilai PWM untuk membuka servo / menjatuhkan barang
SERVO_PWM_CLOSE = 1100    # Nilai PWM standar/tertutup
# ===============================================

# Definisi State Mesin
STATE_HOVER_WP1 = 0
STATE_MOVE_WP2 = 1
STATE_CENTER_BOX = 2
STATE_DROP_PAYLOAD = 3
STATE_HOVER_DONE = 4

app = Flask(__name__)
output_frame = None
lock = threading.Lock()

def connect_pixhawk(port, baudrate):
    print(f"Mencoba terhubung ke Pixhawk di {port} (Baudrate: {baudrate})...")
    master = mavutil.mavlink_connection(port, baud=baudrate)
    master.wait_heartbeat()
    print("✅ Berhasil Terhubung ke Pixhawk!")
    master.mav.request_data_stream_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1
    )
    return master

def send_velocity(master, vx, vy, vz):
    master.mav.set_position_target_local_ned_send(
        0, master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_BODY_NED,
        0b0000111111000111,
        0, 0, 0, vx, vy, vz, 0, 0, 0, 0, 0
    )

def drop_payload(master):
    print("🚀 MENJATUHKAN PAYLOAD (FIRST AID KIT)!")
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_SERVO, 0,
        SERVO_PIN, SERVO_PWM_OPEN, 0, 0, 0, 0, 0
    )

def get_altitude(master, current_alt):
    msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=False)
    if msg:
        return msg.relative_alt / 1000.0
    return current_alt

def detect_red_box(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_red1 = np.array([0, 120, 70])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 120, 70])
    upper_red2 = np.array([180, 255, 255])
    
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = mask1 + mask2
    
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if len(contours) > 0:
        c = max(contours, key=cv2.contourArea)
        if cv2.contourArea(c) > 1000:
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                x, y, w, h = cv2.boundingRect(c)
                return True, (cx, cy), (x, y, w, h)
    return False, (0, 0), (0, 0, 0, 0)

def drone_mission_task(connect_port, baud, camera_index):
    global output_frame, lock

    master = connect_pixhawk(connect_port, baud)
    
    cap = cv2.VideoCapture(camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    if not cap.isOpened():
        print(f"❌ Gagal membuka kamera.")
        return

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_7X7_50)
    aruco_params = cv2.aruco.DetectorParameters()
    try:
        aruco_params.minMarkerPerimeterRate = 0.03
    except:
        pass
    has_new_api = hasattr(cv2.aruco, 'ArucoDetector')
    if has_new_api:
        detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    current_alt = 0.0
    state = STATE_HOVER_WP1
    stable_start_time = 0

    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_SERVO, 0,
        SERVO_PIN, SERVO_PWM_CLOSE, 0, 0, 0, 0, 0
    )

    print("\n🚀 Sistem Misi 2 Siap!")
    print("Mode: GUIDED")
    print("Buka browser di http://localhost:5000 untuk melihat tampilan kamera.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        h, w, _ = frame.shape
        center_x_frame = w // 2
        center_y_frame = h // 2
        
        current_alt = get_altitude(master, current_alt)
        error_alt = TARGET_ALTITUDE - current_alt
        target_vz = np.clip(-1.0 * error_alt * KP_Z, -MAX_SPEED, MAX_SPEED)

        cv2.line(frame, (center_x_frame - 10, center_y_frame), (center_x_frame + 10, center_y_frame), (255, 0, 0), 2)
        cv2.line(frame, (center_x_frame, center_y_frame - 10), (center_x_frame, center_y_frame + 10), (255, 0, 0), 2)

        if state == STATE_HOVER_WP1:
            if has_new_api:
                corners, ids, rejected = detector.detectMarkers(frame)
            else:
                corners, ids, rejected = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=aruco_params)

            if ids is not None and len(ids) > 0:
                points = corners[0][0]
                cx = int(np.mean(points[:, 0]))
                cy = int(np.mean(points[:, 1]))
                cv2.aruco.drawDetectedMarkers(frame, corners, ids)
                cv2.line(frame, (center_x_frame, center_y_frame), (cx, cy), (0, 255, 255), 2)
                
                error_x = cx - center_x_frame
                error_y = cy - center_y_frame
                
                target_vx = np.clip(-1.0 * error_y * KP_XY, -MAX_SPEED, MAX_SPEED)
                target_vy = np.clip(1.0 * error_x * KP_XY, -MAX_SPEED, MAX_SPEED)
                
                send_velocity(master, target_vx, target_vy, target_vz)
                
                if abs(error_x) < 40 and abs(error_y) < 40:
                    if stable_start_time == 0:
                        stable_start_time = time.time()
                    elif time.time() - stable_start_time > 3.0:
                        print("✅ Stabil di WP1. Memulai pergerakan ke WP2!")
                        state = STATE_MOVE_WP2
                else:
                    stable_start_time = 0
                
                cv2.putText(frame, "STATE 0: HOVER WP1", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            else:
                send_velocity(master, 0.0, 0.0, target_vz)
                cv2.putText(frame, "MENCARI ARUCO WP1", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        elif state == STATE_MOVE_WP2:
            red_detected, red_center, red_box = detect_red_box(frame)
            
            if red_detected:
                print("🎯 BOX MERAH DITEMUKAN! Memulai Penyelarasan (Centering)...")
                state = STATE_CENTER_BOX
                stable_start_time = 0
            else:
                send_velocity(master, FORWARD_SPEED, 0.0, target_vz)
                cv2.putText(frame, "STATE 1: MAJU KE WP2 (MENCARI BOX MERAH)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        elif state == STATE_CENTER_BOX:
            red_detected, red_center, red_box = detect_red_box(frame)
            
            if red_detected:
                cx, cy = red_center
                x, y, w, h = red_box
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 3)
                cv2.line(frame, (center_x_frame, center_y_frame), (cx, cy), (0, 255, 255), 2)
                
                error_x = cx - center_x_frame
                error_y = cy - center_y_frame
                
                target_vx = np.clip(-1.0 * error_y * KP_XY, -MAX_SPEED, MAX_SPEED)
                target_vy = np.clip(1.0 * error_x * KP_XY, -MAX_SPEED, MAX_SPEED)
                
                send_velocity(master, target_vx, target_vy, target_vz)
                
                if abs(error_x) < 40 and abs(error_y) < 40:
                    if stable_start_time == 0:
                        stable_start_time = time.time()
                    elif time.time() - stable_start_time > 3.0:
                        print("✅ Target Terkunci! Menjatuhkan Payload...")
                        state = STATE_DROP_PAYLOAD
                        stable_start_time = time.time()
                else:
                    stable_start_time = 0
                
                cv2.putText(frame, "STATE 2: CENTERING BOX MERAH", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                send_velocity(master, 0.0, 0.0, target_vz)
                cv2.putText(frame, "KEHILANGAN BOX MERAH!", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        elif state == STATE_DROP_PAYLOAD:
            drop_payload(master)
            send_velocity(master, 0.0, 0.0, target_vz)
            cv2.putText(frame, "STATE 3: DROPPING PAYLOAD!!!", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 3)
            
            if time.time() - stable_start_time > 3.0:
                state = STATE_HOVER_DONE

        elif state == STATE_HOVER_DONE:
            send_velocity(master, 0.0, 0.0, target_vz)
            cv2.putText(frame, "MISI 2 SELESAI. HOVERING DI WP2", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        master.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_GCS,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0
        )
        
        # Simpan frame ke variabel global agar bisa dibaca oleh Flask
        with lock:
            output_frame = frame.copy()

    cap.release()


def generate():
    global output_frame, lock
    while True:
        with lock:
            if output_frame is None:
                continue
            (flag, encodedImage) = cv2.imencode(".jpg", output_frame)
            if not flag:
                continue
        
        yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')

@app.route("/")
def index():
    html_page = """
    <html>
      <head>
        <title>Misi 2: Pengiriman Medis Otonom</title>
        <style>
            body { background-color: #1a1a1a; color: white; font-family: Arial, sans-serif; text-align: center; }
            img { max-width: 100%; height: auto; border: 3px solid #333; border-radius: 10px; }
            .container { margin-top: 50px; }
        </style>
      </head>
      <body>
        <div class="container">
            <h1>Video Stream Drone KRTI</h1>
            <img src="/video_feed" />
        </div>
      </body>
    </html>
    """
    return html_page

@app.route("/video_feed")
def video_feed():
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")




if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Misi 2 VTOL (Web): WP1 ke WP2, Deteksi Box Merah, Drop Payload')
    parser.add_argument('--connect', default=PIXHAWK_PORT, help="Port Pixhawk")
    parser.add_argument('--baud', type=int, default=PIXHAWK_BAUD, help="Baudrate Pixhawk")
    parser.add_argument('--camera', type=int, default=CAMERA_INDEX, help="Index kamera")
    args = parser.parse_args()

    # Mulai thread drone di background
    t = threading.Thread(target=drone_mission_task, args=(args.connect, args.baud, args.camera))
    t.daemon = True
    t.start()

    # Mulai Flask server
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, use_reloader=False)
