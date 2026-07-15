#!/usr/bin/env python3
"""
Integrasi Kamera & Pixhawk (Pymavlink) untuk Mendeteksi ArUco Marker (7x7)
dan Hover Tepat di Atasnya pada ketinggian 1.5 Meter.
"""

import cv2
import time
import argparse
import numpy as np
from pymavlink import mavutil

# ================= KONFIGURASI =================
TARGET_ALTITUDE = 1.5   # Target ketinggian (meter)
KP_XY = 0.005           # Proportional gain sumbu X dan Y (pixel kamera ke meter/s)
KP_Z = 0.5              # Proportional gain untuk ketinggian
MAX_SPEED = 0.5         # Kecepatan maksimal drone (m/s)
# ===============================================

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
        0,
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_BODY_NED,
        0b0000111111000111,
        0, 0, 0,
        vx, vy, vz,
        0, 0, 0,
        0, 0
    )

def get_altitude(master, current_alt):
    msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=False)
    if msg:
        return msg.relative_alt / 1000.0
    return current_alt

def main():
    parser = argparse.ArgumentParser(description='Dual Gate ArUco Center PID Hovering')
    parser.add_argument('--connect', default='/dev/ttyACM0', help="Port Pixhawk")
    parser.add_argument('--baud', type=int, default=115200, help="Baudrate Pixhawk")
    parser.add_argument('--camera', type=int, default=1, help="Index kamera (ganti 0 jika webcam bawaan)")
    args = parser.parse_args()

    # Inisialisasi koneksi Pixhawk
    master = connect_pixhawk(args.connect, args.baud)
    
    # Inisialisasi Kamera dengan Resolusi 720p
    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    if not cap.isOpened():
        print(f"❌ Gagal membuka kamera dengan index {args.camera}")
        return

    # Inisialisasi ArUco 7x7
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

    print("\n🚀 Sistem Siap!")
    print("Bawa drone terbang, pindahkan ke mode GUIDED, dan drone akan mulai menengahkan marker otomatis.")
    print("Tekan tombol 'q' pada jendela video untuk keluar.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        h, w, _ = frame.shape
        center_x_frame = w // 2
        center_y_frame = h // 2
        
        current_alt = get_altitude(master, current_alt)

        cv2.line(frame, (center_x_frame - 10, center_y_frame), (center_x_frame + 10, center_y_frame), (255, 0, 0), 2)
        cv2.line(frame, (center_x_frame, center_y_frame - 10), (center_x_frame, center_y_frame + 10), (255, 0, 0), 2)

        if has_new_api:
            corners, ids, rejected = detector.detectMarkers(frame)
        else:
            corners, ids, rejected = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=aruco_params)

        if ids is not None and len(ids) > 0:
            points = corners[0][0]
            
            qr_center_x = int(np.mean(points[:, 0]))
            qr_center_y = int(np.mean(points[:, 1]))

            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
            cv2.circle(frame, (qr_center_x, qr_center_y), 5, (0, 0, 255), -1)
            cv2.line(frame, (center_x_frame, center_y_frame), (qr_center_x, qr_center_y), (0, 255, 255), 2)
            
            error_x_pixel = qr_center_x - center_x_frame
            error_y_pixel = qr_center_y - center_y_frame
            
            target_vx = -1.0 * error_y_pixel * KP_XY
            target_vy = 1.0 * error_x_pixel * KP_XY
            
            error_alt = TARGET_ALTITUDE - current_alt
            target_vz = -1.0 * error_alt * KP_Z
            
            target_vx = np.clip(target_vx, -MAX_SPEED, MAX_SPEED)
            target_vy = np.clip(target_vy, -MAX_SPEED, MAX_SPEED)
            target_vz = np.clip(target_vz, -MAX_SPEED, MAX_SPEED)
            
            send_velocity(master, target_vx, target_vy, target_vz)

            cv2.putText(frame, f"VZ: {target_vz:.2f} | VX: {target_vx:.2f} | VY: {target_vy:.2f}", 
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(frame, f"Alt: {current_alt:.2f}m / Target: 1.5m", 
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(frame, "STATUS: TRACKING MARKER", (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        else:
            error_alt = TARGET_ALTITUDE - current_alt
            target_vz = -1.0 * error_alt * KP_Z
            target_vz = np.clip(target_vz, -MAX_SPEED, MAX_SPEED)
            
            send_velocity(master, 0.0, 0.0, target_vz)
            
            cv2.putText(frame, "MARKER TIDAK DITEMUKAN - HOVERING", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.putText(frame, f"Alt: {current_alt:.2f}m / Target: 1.5m", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        cv2.imshow("Kamera Bawah - Auto ArUco Centering PID", frame)
        
        master.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_GCS,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0
        )
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
