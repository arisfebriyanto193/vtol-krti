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
from flask import Flask, Response, jsonify

# Menambahkan path folder 'main' ke sys.path agar bisa membaca folder 'config'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.main import PIXHAWK_PORT, PIXHAWK_BAUD, CAMERA_INDEX

# ================= KONFIGURASI =================
TARGET_ALTITUDE = 1.5     # Target ketinggian (meter)
KP_XY = 0.008             # Proportional gain sumbu X dan Y (Dinaikkan agar pergerakan centering lebih responsif)
KP_Z = 0.5                # Proportional gain ketinggian
MAX_SPEED = 0.5           # Kecepatan maksimal drone (m/s)
FORWARD_SPEED = 0.5       # Kecepatan maju menuju WP2 (m/s)

# Konfigurasi Servo (Drop Payload)
SERVO_PIN = 9             # Pin servo pada Pixhawk (AUX 1 biasanya pin 9)
SERVO_PWM_OPEN = 1900     # Nilai PWM untuk membuka servo / menjatuhkan barang
SERVO_PWM_CLOSE = 1100    # Nilai PWM standar/tertutup
# ===============================================

# Definisi State Mesin
STATE_WAIT_START = -1
STATE_HOVER_WP1 = 0
STATE_MOVE_WP2 = 1
STATE_CENTER_BOX = 2
STATE_DROP_PAYLOAD = 3
STATE_HOVER_DONE = 4

STATE_NAMES = {
    STATE_WAIT_START: "WAIT START",
    STATE_HOVER_WP1: "HOVER WP1",
    STATE_MOVE_WP2: "MOVE WP2",
    STATE_CENTER_BOX: "CENTERING BOX",
    STATE_DROP_PAYLOAD: "DROP PAYLOAD",
    STATE_HOVER_DONE: "HOVER DONE"
}

app = Flask(__name__)
output_frame = None
lock = threading.Lock()

# Global variable for telemetry
telemetry_data = {
    "altitude": 0.0,
    "battery_voltage": 0.0,
    "battery_remaining": 0,
    "flight_mode": "UNKNOWN",
    "state": "WAIT START",
    "ch8": 0,
    "groundspeed": 0.0
}

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
    print("🚀 [SIMULASI] MENJATUHKAN PAYLOAD (FIRST AID KIT)!")
    print(f"[SIMULASI] Mengirim perintah BUKA ke Servo PIN {SERVO_PIN} dengan PWM {SERVO_PWM_OPEN}")
    # master.mav.command_long_send(...)


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
        if cv2.contourArea(c) > 4000:  # Area dinaikkan dari 1000 ke 4000 untuk meminimalisir deteksi palsu (false-positive)
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
    ch8_value = 0
    state = STATE_WAIT_START
    stable_start_time = 0
    last_mode_request = 0

    print(f"\n[INIT] [SIMULASI] Menutup Servo (PWM {SERVO_PWM_CLOSE}) pada PIN {SERVO_PIN}")
    # master.mav.command_long_send(
    #     master.target_system, master.target_component,
    #     mavutil.mavlink.MAV_CMD_DO_SET_SERVO, 0,
    #     SERVO_PIN, SERVO_PWM_CLOSE, 0, 0, 0, 0, 0
    # )

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
        
        # Mengambil SEMUA pesan MAVLink yang masuk agar tidak saling overwrite
        while True:
            msg = master.recv_match(blocking=False)
            if not msg:
                break
            msg_type = msg.get_type()
            if msg_type == 'GLOBAL_POSITION_INT':
                current_alt = msg.relative_alt / 1000.0
                telemetry_data["altitude"] = current_alt
            elif msg_type == 'RC_CHANNELS':
                ch8_value = msg.chan8_raw
                telemetry_data["ch8"] = ch8_value
            elif msg_type == 'SYS_STATUS':
                telemetry_data["battery_voltage"] = msg.voltage_battery / 1000.0
                telemetry_data["battery_remaining"] = msg.battery_remaining
            elif msg_type == 'HEARTBEAT':
                if master.mode_mapping():
                    for name, code in master.mode_mapping().items():
                        if code == msg.custom_mode:
                            telemetry_data["flight_mode"] = name
                            break
            elif msg_type == 'VFR_HUD':
                telemetry_data["groundspeed"] = msg.groundspeed
        
        telemetry_data["state"] = STATE_NAMES.get(state, "UNKNOWN")
        
        error_alt = TARGET_ALTITUDE - current_alt
        target_vz = np.clip(-1.0 * error_alt * KP_Z, -MAX_SPEED, MAX_SPEED)

        cv2.line(frame, (center_x_frame - 10, center_y_frame), (center_x_frame + 10, center_y_frame), (255, 0, 0), 2)
        cv2.line(frame, (center_x_frame, center_y_frame - 10), (center_x_frame, center_y_frame + 10), (255, 0, 0), 2)

        if state == STATE_WAIT_START:
            cv2.putText(frame, f"MENUNGGU START! (CH 8: {ch8_value})", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
            cv2.putText(frame, "Nyalakan CH 8 (> 1900) untuk GUIDED mode", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            if ch8_value > 1900:
                print("✅ Sinyal CH 8 terdeteksi! Mengubah mode ke GUIDED...")
                if master.mode_mapping() and 'GUIDED' in master.mode_mapping():
                    mode_id = master.mode_mapping()['GUIDED']
                    master.mav.command_long_send(
                        master.target_system, master.target_component,
                        mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
                        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                        mode_id, 0, 0, 0, 0, 0
                    )
                state = STATE_HOVER_WP1
                last_mode_request = time.time()

        # ================= FITUR SAFETY & MODE ENFORCER =================
        if state != STATE_WAIT_START:
            # 1. Jika Pilot mematikan switch CH 8, batalkan misi
            if ch8_value < 1900:
                print("🛑 CH 8 DIMATIKAN! Membatalkan misi dan kembali ke mode tunggu...")
                state = STATE_WAIT_START
                continue
            
            # 2. Jika Flight Controller otomatis keluar dari GUIDED (misal STABILIZE karena jitter remot/failsafe)
            if telemetry_data["flight_mode"] != "GUIDED" and telemetry_data["flight_mode"] != "UNKNOWN":
                cv2.putText(frame, f"PERINGATAN: MODE {telemetry_data['flight_mode']} (BUKAN GUIDED)!", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                # Paksa kembali ke GUIDED maksimal 1 kali setiap 2 detik agar tidak spam
                if time.time() - last_mode_request > 2.0:
                    print(f"⚠️ Peringatan: Mode berubah ke {telemetry_data['flight_mode']}. Memaksa kembali ke GUIDED...")
                    if master.mode_mapping() and 'GUIDED' in master.mode_mapping():
                        mode_id = master.mode_mapping()['GUIDED']
                        master.mav.command_long_send(
                            master.target_system, master.target_component,
                            mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
                            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                            mode_id, 0, 0, 0, 0, 0
                        )
                    last_mode_request = time.time()
        # ================================================================

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
                
                if abs(error_x) < 80 and abs(error_y) < 80:  # Toleransi radius diperlebar ke 80px (sekitar ~6% layar)
                    if stable_start_time == 0:
                        stable_start_time = time.time()
                    elif time.time() - stable_start_time > 2.0:  # Waktu tahan dipersingkat ke 2 detik agar tidak terlalu lama
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
                
                if abs(error_x) < 80 and abs(error_y) < 80:  # Toleransi radius diperlebar
                    if stable_start_time == 0:
                        stable_start_time = time.time()
                    elif time.time() - stable_start_time > 2.0:  # Waktu tahan dipersingkat
                        print("✅ Target Terkunci! Menjatuhkan Payload...")
                        state = STATE_DROP_PAYLOAD
                        stable_start_time = time.time()
                else:
                    stable_start_time = 0
                
                cv2.putText(frame, "STATE 2: CENTERING BOX MERAH", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                # Perbaikan Bug: Jika kotak merah hilang (karena deteksi palsu sebelumnya), drone harus KEMBALI MAJU (MOVE WP2)
                print("⚠️ Kehilangan Box Merah! Kembali ke mode pencarian (maju)...")
                state = STATE_MOVE_WP2
                stable_start_time = 0

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
            body { background-color: #121212; color: white; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; margin: 0; padding: 20px; }
            h1 { color: #00d2ff; font-weight: 300; margin-bottom: 30px; }
            .main-container { display: flex; flex-direction: column; align-items: center; justify-content: center; max-width: 1200px; margin: auto; }
            .video-container { position: relative; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.8); border-radius: 12px; overflow: hidden; border: 1px solid #333; max-width: 800px; width: 100%; background: #000; }
            img { max-width: 100%; height: auto; display: block; }
            
            .telemetry-dashboard { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; width: 100%; max-width: 900px; }
            .telemetry-card { background: #1e1e1e; border: 1px solid #2a2a2a; border-radius: 12px; padding: 20px; flex: 1; min-width: 180px; box-shadow: 0 4px 15px rgba(0,0,0,0.4); transition: transform 0.2s ease; }
            .telemetry-card:hover { transform: translateY(-3px); border-color: #444; }
            .telemetry-card h3 { margin: 0 0 12px 0; font-size: 13px; color: #aaa; text-transform: uppercase; letter-spacing: 1px; }
            .telemetry-card .value { font-size: 26px; font-weight: 600; color: #fff; }
            .highlight { color: #00d2ff !important; text-shadow: 0 0 10px rgba(0, 210, 255, 0.3); }
            .warning { color: #ff4a4a !important; text-shadow: 0 0 10px rgba(255, 74, 74, 0.3); }
            .success { color: #00ff88 !important; text-shadow: 0 0 10px rgba(0, 255, 136, 0.3); }
        </style>
        <script>
            function fetchTelemetry() {
                fetch('/telemetry')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('alt-val').innerText = data.altitude.toFixed(2) + ' m';
                        
                        let batStr = data.battery_voltage > 0 ? data.battery_voltage.toFixed(2) + ' V (' + data.battery_remaining + '%)' : '0.00 V (0%)';
                        document.getElementById('bat-val').innerText = batStr;
                        
                        if (data.battery_remaining < 20 && data.battery_voltage > 0) {
                            document.getElementById('bat-val').className = 'value warning';
                        } else {
                            document.getElementById('bat-val').className = 'value success';
                        }

                        document.getElementById('mode-val').innerText = data.flight_mode;
                        document.getElementById('state-val').innerText = data.state;
                        document.getElementById('speed-val').innerText = data.groundspeed.toFixed(2) + ' m/s';
                        document.getElementById('ch8-val').innerText = data.ch8;
                    })
                    .catch(err => console.error("Error fetching telemetry:", err));
            }
            setInterval(fetchTelemetry, 500);
        </script>
      </head>
      <body>
        <div class="main-container">
            <h1>Sistem Pemantauan Misi VTOL</h1>
            
            <div class="video-container">
                <img src="/video_feed" />
            </div>

            <div class="telemetry-dashboard">
                <div class="telemetry-card">
                    <h3>State Misi</h3>
                    <div class="value highlight" id="state-val">--</div>
                </div>
                <div class="telemetry-card">
                    <h3>Flight Mode</h3>
                    <div class="value" id="mode-val">--</div>
                </div>
                <div class="telemetry-card">
                    <h3>Ketinggian</h3>
                    <div class="value" id="alt-val">-- m</div>
                </div>
                <div class="telemetry-card">
                    <h3>Baterai</h3>
                    <div class="value" id="bat-val">-- V (--%)</div>
                </div>
                <div class="telemetry-card">
                    <h3>Kecepatan</h3>
                    <div class="value" id="speed-val">-- m/s</div>
                </div>
                <div class="telemetry-card">
                    <h3>CH 8 (Trigger)</h3>
                    <div class="value" id="ch8-val">--</div>
                </div>
            </div>
        </div>
      </body>
    </html>
    """
    return html_page

@app.route("/telemetry")
def telemetry():
    return jsonify(telemetry_data)

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
