#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Misi Otonom VTOL: WP1 (Manual) -> WP2 (Otonom Kanan) -> WP3 (Otonom Maju) -> WP4 (Otonom Serong)
Menggunakan deteksi ArUco Marker 7x7 pada masing-masing Waypoint.
"""

import os
import sys
import cv2
import time
import argparse
import numpy as np
from pymavlink import mavutil

# Menambahkan path folder 'main' ke sys.path agar bisa membaca folder 'config' & 'web_dashboard'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

try:
    from config.main import PIXHAWK_PORT, PIXHAWK_BAUD, CAMERA_INDEX
except ImportError:
    PIXHAWK_PORT = '/dev/ttyACM0'
    PIXHAWK_BAUD = 115200
    CAMERA_INDEX = 0

try:
    from web_dashboard import start_web_server, update_web_data
    HAS_DASHBOARD = True
except ImportError:
    HAS_DASHBOARD = False
    def start_web_server(port=5000): pass
    def update_web_data(frame, telemetry): pass

# ======================= KONFIGURASI MISI =======================
TARGET_ALTITUDE = 1.5       # Target ketinggian (meter)
KP_XY = 0.0015              # Proportional gain sumbu X dan Y (Centering)
KP_Z = 0.5                  # Proportional gain sumbu Z (Altitude)
MAX_SPEED = 0.3             # Kecepatan maksimal saat centering (m/s)
FORWARD_SPEED = 0.4         # Kecepatan otonom saat bergerak antar WP (m/s)
LOCK_TOLERANCE = 40         # Toleransi jarak center marker (pixel)
STABLE_DURATION = 3.0       # Waktu drone harus stabil di tengah marker sebelum lanjut (detik)
SEARCH_TIMEOUT = 20.0       # Batas waktu pencarian marker berikutnya sebelum masuk mode Failsafe (detik)

# Target ID ArUco di masing-masing Waypoint
TARGET_ID_WP1 = 1
TARGET_ID_WP2 = 2
TARGET_ID_WP3 = 3
TARGET_ID_WP4 = 4

# Tipe Kamus ArUco (Ganti ke DICT_7X7_50 atau DICT_7X7_1000 sesuai kebutuhan)
ARUCO_DICT_TYPE = cv2.aruco.DICT_7X7_50

# Arah pergerakan otonom antar Waypoint (dalam frame BODY_NED):
# 1. Dari WP1 ke WP2: Menyamping Kanan (vx = 0, vy = +FORWARD_SPEED)
WP1_TO_WP2_VX = 0.0
WP1_TO_WP2_VY = FORWARD_SPEED

# 2. Dari WP2 ke WP3: Lurus Maju (vx = +FORWARD_SPEED, vy = 0)
WP2_TO_WP3_VX = FORWARD_SPEED
WP2_TO_WP3_VY = 0.0

# 3. Dari WP3 ke WP4: Serong/Diagonal Kanan-Depan
# vx = speed * cos(45 deg), vy = speed * sin(45 deg) -> total speed = FORWARD_SPEED
WP3_TO_WP4_VX = FORWARD_SPEED * 0.707
WP3_TO_WP4_VY = FORWARD_SPEED * 0.707
# ================================================================

# Definisi State Machine
STATE_CENTER_WP1     = 0    # Centering di atas WP1 (ArUco ID 1)
STATE_MOVE_TO_WP2    = 1    # Terbang otonom menyamping kanan mencari WP2
STATE_CENTER_WP2     = 2    # Centering di atas WP2 (ArUco ID 2)
STATE_MOVE_TO_WP3    = 3    # Terbang otonom maju mencari WP3
STATE_CENTER_WP3     = 4    # Centering di atas WP3 (ArUco ID 3)
STATE_MOVE_TO_WP4    = 5    # Terbang otonom serong kanan-depan mencari WP4
STATE_CENTER_WP4     = 6    # Centering di atas WP4 (ArUco ID 4)
STATE_LAND_WP4       = 7    # Proses landing otonom di WP4
STATE_MISSION_DONE   = 8    # Misi selesai (Hover aman)
STATE_FAILSAFE_HOVER = 9    # Failsafe Hover jika marker tidak ditemukan dalam batas waktu

STATE_NAMES = {
    STATE_CENTER_WP1: "CENTERING WP1 (ID 1)",
    STATE_MOVE_TO_WP2: "MAJU KE WP2 (KANAN)",
    STATE_CENTER_WP2: "CENTERING WP2 (ID 2)",
    STATE_MOVE_TO_WP3: "MAJU KE WP3 (MAJU)",
    STATE_CENTER_WP3: "CENTERING WP3 (ID 3)",
    STATE_MOVE_TO_WP4: "MAJU KE WP4 (SERONG)",
    STATE_CENTER_WP4: "CENTERING WP4 (ID 4)",
    STATE_LAND_WP4: "LANDING AT WP4",
    STATE_MISSION_DONE: "MISI SELESAI (HOVER)",
    STATE_FAILSAFE_HOVER: "FAILSAFE HOVER (TIMEOUT)"
}

def connect_pixhawk(port, baudrate):
    print(f"Menghubungkan ke Pixhawk di {port} (Baudrate: {baudrate})...")
    master = mavutil.mavlink_connection(port, baud=baudrate)
    master.wait_heartbeat()
    print("✅ Berhasil Terhubung ke Pixhawk!")
    master.mav.request_data_stream_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1
    )
    return master

def send_velocity(master, vx, vy, vz):
    """Mengirim perintah kecepatan dalam frame BODY_NED."""
    if master is None:
        # Simulasi offline, tidak mengirim command MAVLink
        return
    master.mav.set_position_target_local_ned_send(
        0, master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_BODY_NED,
        0b0000111111000111, # Mask bit untuk mengabaikan posisi, akselerasi, yaw rate
        0, 0, 0, vx, vy, vz, 0, 0, 0, 0, 0
    )

def land_drone(master):
    """Mengirim perintah LAND otonom."""
    print("⚠️ Mengirim Perintah LAND (Landing)...")
    if master is None:
        print("[SIMULATION] Drone mendarat otonom (LAND) di WP4.")
        return
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_NAV_LAND, 0,
        0, 0, 0, 0, 0, 0, 0
    )

def get_altitude(master, current_alt):
    """Mengambil ketinggian drone dari Pixhawk."""
    while True:
        msg = master.recv_match(type=['GLOBAL_POSITION_INT', 'LOCAL_POSITION_NED', 'RANGEFINDER'], blocking=False)
        if not msg:
            break
        
        msg_type = msg.get_type()
        if msg_type == 'GLOBAL_POSITION_INT':
            current_alt = msg.relative_alt / 1000.0  # mm ke meter
        elif msg_type == 'LOCAL_POSITION_NED':
            current_alt = -msg.z  # Z negatif berarti naik
        elif msg_type == 'RANGEFINDER':
            current_alt = msg.distance  # Jarak lidar
    return current_alt

def get_flight_mode(master):
    """Mengambil mode penerbangan saat ini."""
    msg = master.recv_match(type='HEARTBEAT', blocking=False)
    if msg:
        try:
            return mavutil.mode_string_v10(msg)
        except:
            return "UNKNOWN"
    return None

def draw_visuals(frame, cx, cy, marker_id, error_x, error_y, is_locked, 
                 center_x_frame, center_y_frame, state_name, altitude, 
                 vx, vy, vz, is_test_mode=False):
    """Menggambar HUD informasi visual di layar kamera."""
    # Warna HUD
    color_locked = (0, 255, 0)      # Hijau
    color_tracking = (0, 165, 255)  # Oranye
    color_cross = (255, 0, 0)       # Biru
    color_text = (255, 255, 255)    # Putih

    # 1. Gambar Crosshair titik tengah kamera
    cv2.line(frame, (center_x_frame - 20, center_y_frame), (center_x_frame + 20, center_y_frame), color_cross, 2)
    cv2.line(frame, (center_x_frame, center_y_frame - 20), (center_x_frame, center_y_frame + 20), color_cross, 2)

    # 2. Lingkaran toleransi LOCK
    cv2.circle(frame, (center_x_frame, center_y_frame), LOCK_TOLERANCE, color_locked if is_locked else (80, 80, 80), 1)

    # 3. Jika marker terdeteksi
    if cx is not None and cy is not None:
        color_box = color_locked if is_locked else color_tracking
        cv2.circle(frame, (cx, cy), 6, color_box, -1)
        cv2.line(frame, (center_x_frame, center_y_frame), (cx, cy), (0, 255, 255), 2)

    # 4. Gambar panel informasi semi-transparan di kiri atas
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (460, 205), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

    # Isi teks informasi
    status_text = "LOCKED" if is_locked else ("TRACKING" if cx is not None else "SEARCHING")
    status_color = color_locked if is_locked else (color_tracking if cx is not None else (0, 0, 255))

    cv2.putText(frame, f"STATE    : {state_name}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
    cv2.putText(frame, f"STATUS   : {status_text}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
    cv2.putText(frame, f"ALTITUDE : {altitude:.2f} m" if altitude is not None else "ALTITUDE : N/A", (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_text, 2)
    if cx is not None:
        cv2.putText(frame, f"MARKER ID: {marker_id}", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_text, 2)
        cv2.putText(frame, f"ERROR X  : {error_x:+d} px", (10, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_text, 2)
        cv2.putText(frame, f"ERROR Y  : {error_y:+d} px", (10, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_text, 2)
    else:
        cv2.putText(frame, "MARKER ID: NONE", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # Info Kecepatan
    cv2.putText(frame, f"VEL OUT  : vx={vx:+.2f} vy={vy:+.2f} vz={vz:+.2f} m/s", (10, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    if is_test_mode:
        cv2.putText(frame, "TEST MODE (NO PIXHAWK)", (10, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    return frame

def main():
    parser = argparse.ArgumentParser(description='Program Misi Otonom Waypoint ArUco (WP1 -> WP2 -> WP3 -> WP4)')
    parser.add_argument('--connect', default=PIXHAWK_PORT, help="Port Pixhawk (e.g. COMx or /dev/ttyACM0)")
    parser.add_argument('--baud', type=int, default=PIXHAWK_BAUD, help="Baudrate Pixhawk")
    parser.add_argument('--camera', type=int, default=CAMERA_INDEX, help="Index kamera")
    parser.add_argument('--test-cam', action='store_true', help="Mode tes kamera offline tanpa koneksi Pixhawk")
    args = parser.parse_args()

    # Hubungkan ke Pixhawk (jika bukan mode tes)
    if args.test_cam:
        print("\n[TEST MODE] Menjalankan simulasi deteksi kamera OFFLINE (Tanpa Pixhawk).")
        master = None
    else:
        master = connect_pixhawk(args.connect, args.baud)

    # Inisialisasi Kamera (Gunakan DirectShow di Windows agar tidak hang, dan resolusi 640x480)
    if os.name == 'nt':
        cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(args.camera)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("❌ [ERROR] Gagal membuka kamera.")
        return

    # Inisialisasi Detektor ArUco
    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT_TYPE)
    aruco_params = cv2.aruco.DetectorParameters()
    try:
        aruco_params.minMarkerPerimeterRate = 0.01
    except:
        pass

    has_new_api = hasattr(cv2.aruco, 'ArucoDetector')
    if has_new_api:
        detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    # Start dashboard server jika tersedia
    if HAS_DASHBOARD:
        start_web_server(port=5000)

    # Inisialisasi Telemetri Awal
    current_alt = 1.0
    state = STATE_CENTER_WP1
    stable_start_time = 0
    search_start_time = time.time()  # Penanda waktu mulai mencari marker otonom
    current_mode = "LOITER" if not args.test_cam else "GUIDED"

    print("\n🚀 Sistem Otonom Multi-Waypoint Siap!")
    print("-----------------------------------------------------------------")
    if args.test_cam:
        print("[INFO] Jalankan tes dengan menunjukkan ArUco Marker ke kamera:")
        print(f"       - WP1: Tunjukkan ArUco ID {TARGET_ID_WP1}")
        print(f"       - WP2: Tunjukkan ArUco ID {TARGET_ID_WP2}")
        print(f"       - WP3: Tunjukkan ArUco ID {TARGET_ID_WP3}")
        print(f"       - WP4: Tunjukkan ArUco ID {TARGET_ID_WP4}")
    else:
        print("Langkah Pertama: Terbang MANUAL drone Anda di atas WP1.")
        print("Setelah siap di WP1, ubah Mode terbang ke GUIDED untuk memulai otonom!")
    print("-----------------------------------------------------------------\n")

    try:
        while True:
            target_vx = 0.0
            target_vy = 0.0

            # 1. Update data mode & ketinggian dari Pixhawk
            if master is not None:
                mode_update = get_flight_mode(master)
                if mode_update:
                    current_mode = mode_update

                current_alt = get_altitude(master, current_alt)
                
                # Hitung kecepatan koreksi Altitude (vz)
                error_alt = TARGET_ALTITUDE - current_alt
                target_vz = np.clip(-1.0 * error_alt * KP_Z, -MAX_SPEED, MAX_SPEED)
            else:
                # Mode Simulasi Kamera Offline
                current_mode = "GUIDED"
                current_alt = TARGET_ALTITUDE
                target_vz = 0.0

            # 2. Baca Frame Kamera
            ret, frame = cap.read()
            if not ret or frame is None:
                print("⚠️ [WARNING] Gagal membaca frame kamera! Berhenti otonom demi keamanan.")
                send_velocity(master, 0.0, 0.0, target_vz)
                time.sleep(0.1)
                continue

            h, w, _ = frame.shape
            center_x_frame = w // 2
            center_y_frame = h // 2

            # 3. Deteksi Marker ArUco
            if has_new_api:
                corners, ids, rejected = detector.detectMarkers(frame)
            else:
                corners, ids, rejected = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=aruco_params)

            # Visualizer frame (canvas untuk dashboard/layar lokal)
            display_frame = frame.copy()

            # Variabel deteksi marker saat ini
            target_marker_found = False
            cx, cy = None, None
            error_x, error_y = 0, 0
            is_locked = False
            target_id_for_state = None

            # Tentukan ID ArUco target berdasarkan state saat ini
            if state in [STATE_CENTER_WP1]:
                target_id_for_state = TARGET_ID_WP1
            elif state in [STATE_MOVE_TO_WP2, STATE_CENTER_WP2]:
                target_id_for_state = TARGET_ID_WP2
            elif state in [STATE_MOVE_TO_WP3, STATE_CENTER_WP3]:
                target_id_for_state = TARGET_ID_WP3
            elif state in [STATE_MOVE_TO_WP4, STATE_CENTER_WP4]:
                target_id_for_state = TARGET_ID_WP4

            # Cari apakah target marker ada di dalam hasil deteksi kamera
            if ids is not None and target_id_for_state is not None:
                if target_id_for_state in ids:
                    target_marker_found = True
                    idx = np.where(ids == target_id_for_state)[0][0]
                    points = corners[idx][0]
                    
                    # Hitung koordinat tengah marker
                    cx = int(np.mean(points[:, 0]))
                    cy = int(np.mean(points[:, 1]))
                    
                    # Hitung error piksel terhadap pusat frame
                    error_x = cx - center_x_frame
                    error_y = cy - center_y_frame
                    
                    # Status Kunci target (jika error di bawah batas toleransi)
                    is_locked = abs(error_x) < LOCK_TOLERANCE and abs(error_y) < LOCK_TOLERANCE
                    
                    # Gambar kotak deteksi marker target di frame visual
                    cv2.aruco.drawDetectedMarkers(display_frame, [corners[idx]], np.array([[target_id_for_state]]))

            # ================= LOGIKA FLIGHT MODE CONTROLLER =================
            # Jika drone TIDAK dalam mode GUIDED, cetak warning dan jangan kirim command otonom (biarkan pilot memegang kendali manual)
            if current_mode != "GUIDED":
                # Reset penanda waktu stabilitas agar tidak terpicu secara tidak sengaja
                stable_start_time = 0
                search_start_time = time.time()
                
                # Tampilkan info mode non-guided di layar
                cv2.putText(display_frame, f"MODE: {current_mode} (Bukan GUIDED!)", (10, h - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                cv2.putText(display_frame, "Aktifkan GUIDED untuk mulai Otonom", (10, h - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            else:
                # JIKA MODE GUIDED AKTIF, LOGIKA STATE MACHINE DIJALANKAN:
                
                # --- STATE 0: CENTERING DI WP1 ---
                if state == STATE_CENTER_WP1:
                    if target_marker_found:
                        # Menghitung output kecepatan menggunakan P-Controller
                        target_vx = np.clip(-1.0 * error_y * KP_XY, -MAX_SPEED, MAX_SPEED)
                        target_vy = np.clip(1.0 * error_x * KP_XY, -MAX_SPEED, MAX_SPEED)
                        send_velocity(master, target_vx, target_vy, target_vz)
                        
                        # Cek durasi stabilitas
                        if is_locked:
                            if stable_start_time == 0:
                                stable_start_time = time.time()
                            elif time.time() - stable_start_time > STABLE_DURATION:
                                print(f"✅ WP1 Locked! Memulai otonom ke WP2 (Kanan)...")
                                state = STATE_MOVE_TO_WP2
                                stable_start_time = 0
                                search_start_time = time.time() # Mulai timer pencarian WP2
                        else:
                            stable_start_time = 0
                    else:
                        # Jika tidak mendeteksi marker di awal, hover di tempat
                        send_velocity(master, 0.0, 0.0, target_vz)
                        stable_start_time = 0

                # --- STATE 1: MAJU OTONOM KE WP2 (KANAN) ---
                elif state == STATE_MOVE_TO_WP2:
                    # Cek timeout failsafe (dinonaktifkan saat --test-cam)
                    timeout_reached = (not args.test_cam) and (time.time() - search_start_time > SEARCH_TIMEOUT)
                    if timeout_reached:
                        print(f"[FAILSAFE] Gagal menemukan ArUco WP2 dalam {SEARCH_TIMEOUT} detik! Hover...")
                        state = STATE_FAILSAFE_HOVER
                    # Cek apakah target WP2 sudah terdeteksi
                    elif target_marker_found:
                        print("[OK] ArUco WP2 Ditemukan! Menghentikan gerakan maju & centering...")
                        state = STATE_CENTER_WP2
                        stable_start_time = 0
                    else:
                        # Kirim kecepatan konstan menyamping ke kanan
                        send_velocity(master, WP1_TO_WP2_VX, WP1_TO_WP2_VY, target_vz)

                # --- STATE 2: CENTERING DI WP2 ---
                elif state == STATE_CENTER_WP2:
                    if target_marker_found:
                        target_vx = np.clip(-1.0 * error_y * KP_XY, -MAX_SPEED, MAX_SPEED)
                        target_vy = np.clip(1.0 * error_x * KP_XY, -MAX_SPEED, MAX_SPEED)
                        send_velocity(master, target_vx, target_vy, target_vz)
                        
                        if is_locked:
                            if stable_start_time == 0:
                                stable_start_time = time.time()
                            elif time.time() - stable_start_time > STABLE_DURATION:
                                print(f"✅ WP2 Locked! Memulai otonom ke WP3 (Maju)...")
                                state = STATE_MOVE_TO_WP3
                                stable_start_time = 0
                                search_start_time = time.time() # Mulai timer pencarian WP3
                        else:
                            stable_start_time = 0
                    else:
                        # Jika kehilangan marker di tengah centering, hover di tempat
                        send_velocity(master, 0.0, 0.0, target_vz)
                        stable_start_time = 0

                # --- STATE 3: MAJU OTONOM KE WP3 (MAJU) ---
                elif state == STATE_MOVE_TO_WP3:
                    # Cek timeout failsafe (dinonaktifkan saat --test-cam)
                    timeout_reached = (not args.test_cam) and (time.time() - search_start_time > SEARCH_TIMEOUT)
                    if timeout_reached:
                        print(f"[FAILSAFE] Gagal menemukan ArUco WP3 dalam {SEARCH_TIMEOUT} detik! Hover...")
                        state = STATE_FAILSAFE_HOVER
                    elif target_marker_found:
                        print("[OK] ArUco WP3 Ditemukan! Mulai centering...")
                        state = STATE_CENTER_WP3
                        stable_start_time = 0
                    else:
                        # Kirim kecepatan konstan lurus ke depan
                        send_velocity(master, WP2_TO_WP3_VX, WP2_TO_WP3_VY, target_vz)

                # --- STATE 4: CENTERING DI WP3 ---
                elif state == STATE_CENTER_WP3:
                    if target_marker_found:
                        target_vx = np.clip(-1.0 * error_y * KP_XY, -MAX_SPEED, MAX_SPEED)
                        target_vy = np.clip(1.0 * error_x * KP_XY, -MAX_SPEED, MAX_SPEED)
                        send_velocity(master, target_vx, target_vy, target_vz)
                        
                        if is_locked:
                            if stable_start_time == 0:
                                stable_start_time = time.time()
                            elif time.time() - stable_start_time > STABLE_DURATION:
                                print(f"✅ WP3 Locked! Memulai otonom ke WP4 (Serong)...")
                                state = STATE_MOVE_TO_WP4
                                stable_start_time = 0
                                search_start_time = time.time() # Mulai timer pencarian WP4
                        else:
                            stable_start_time = 0
                    else:
                        send_velocity(master, 0.0, 0.0, target_vz)
                        stable_start_time = 0

                # --- STATE 5: MAJU OTONOM KE WP4 (SERONG) ---
                elif state == STATE_MOVE_TO_WP4:
                    # Cek timeout failsafe (dinonaktifkan saat --test-cam)
                    timeout_reached = (not args.test_cam) and (time.time() - search_start_time > SEARCH_TIMEOUT)
                    if timeout_reached:
                        print(f"[FAILSAFE] Gagal menemukan ArUco WP4 dalam {SEARCH_TIMEOUT} detik! Hover...")
                        state = STATE_FAILSAFE_HOVER
                    elif target_marker_found:
                        print("[OK] ArUco WP4 Ditemukan! Mulai centering...")
                        state = STATE_CENTER_WP4
                        stable_start_time = 0
                    else:
                        # Kirim kecepatan konstan serong kanan-depan
                        send_velocity(master, WP3_TO_WP4_VX, WP3_TO_WP4_VY, target_vz)

                # --- STATE 6: CENTERING DI WP4 ---
                elif state == STATE_CENTER_WP4:
                    if target_marker_found:
                        target_vx = np.clip(-1.0 * error_y * KP_XY, -MAX_SPEED, MAX_SPEED)
                        target_vy = np.clip(1.0 * error_x * KP_XY, -MAX_SPEED, MAX_SPEED)
                        send_velocity(master, target_vx, target_vy, target_vz)
                        
                        if is_locked:
                            if stable_start_time == 0:
                                stable_start_time = time.time()
                            elif time.time() - stable_start_time > STABLE_DURATION:
                                print(f"✅ WP4 Locked! Memulai proses Landing Otonom...")
                                state = STATE_LAND_WP4
                                stable_start_time = time.time()
                        else:
                            stable_start_time = 0
                    else:
                        send_velocity(master, 0.0, 0.0, target_vz)
                        stable_start_time = 0

                # --- STATE 7: LANDING OTONOM DI WP4 ---
                elif state == STATE_LAND_WP4:
                    # Kirim perintah land otonom sekali
                    land_drone(master)
                    state = STATE_MISSION_DONE
                    print("✅ Perintah pendaratan terkirim. Misi Otonom Selesai.")

                # --- STATE 8: MISI SELESAI / HOVER AMAN ---
                elif state == STATE_MISSION_DONE:
                    # Tetap kirim heartbeat/command hover biasa
                    send_velocity(master, 0.0, 0.0, 0.0)

                # --- STATE 9: FAILSAFE (HOVER DI TEMPAT) ---
                elif state == STATE_FAILSAFE_HOVER:
                    send_velocity(master, 0.0, 0.0, target_vz)
                    cv2.putText(display_frame, "WARNING: FAILSAFE TIMEOUT!", (10, h - 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    cv2.putText(display_frame, "Kembalikan ke mode manual untuk mengambil alih.", (10, h - 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # 4. Render HUD visual di jendela
            display_frame = draw_visuals(display_frame, cx, cy, target_id_for_state, error_x, error_y, 
                                         is_locked, center_x_frame, center_y_frame, STATE_NAMES[state], current_alt,
                                         target_vx, target_vy, target_vz, args.test_cam)

            # Tampilkan Mode terbang di sudut bawah layar
            cv2.putText(display_frame, f"MODE: {current_mode}", (10, h - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if current_mode == "GUIDED" else (0, 165, 255), 2)

            # Tampilkan video
            cv2.imshow("Misi Otonom Multi-Waypoint ArUco", display_frame)

            # 5. Kirim data telemetri ke Dashboard Web
            if HAS_DASHBOARD:
                telem_data = {
                    "Status": STATE_NAMES[state],
                    "Mode": current_mode,
                    "Altitude (m)": f"{current_alt:.2f}" if current_alt is not None else "N/A",
                    "Target ID": f"{target_id_for_state}",
                    "Target Found": "YA" if target_marker_found else "TIDAK",
                    "Error X (px)": f"{error_x}" if target_marker_found else "0",
                    "Error Y (px)": f"{error_y}" if target_marker_found else "0",
                    "Target Locked": "YA" if is_locked else "TIDAK",
                }
                update_web_data(display_frame, telem_data)

            # 6. Kirim Heartbeat kontinu agar Pixhawk tidak kehilangan koneksi GCS
            if master is not None:
                master.mav.heartbeat_send(
                    mavutil.mavlink.MAV_TYPE_GCS,
                    mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0
                )

            # Tombol Kontrol (Q = keluar, N = lompat state otonom selanjutnya saat simulasi)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('n') and args.test_cam:
                # Cari state otonom berikutnya
                if state in [STATE_CENTER_WP1, STATE_MOVE_TO_WP2, STATE_CENTER_WP2, 
                             STATE_MOVE_TO_WP3, STATE_CENTER_WP3, STATE_MOVE_TO_WP4, STATE_CENTER_WP4]:
                    state += 1
                    stable_start_time = 0
                    search_start_time = time.time()
                    print(f"⏭️ [MANUAL STATE JUMP] Melompat ke: {STATE_NAMES[state]}")

    except KeyboardInterrupt:
        print("\n🛑 Program dihentikan oleh user (Ctrl+C).")
    finally:
        # Hentikan drone saat keluar demi keamanan
        try:
            send_velocity(master, 0.0, 0.0, 0.0)
        except:
            pass
        cap.release()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
