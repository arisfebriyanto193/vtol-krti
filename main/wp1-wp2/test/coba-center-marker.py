
#!/usr/bin/env python3
import os
import sys
import cv2
import time
import argparse
import numpy as np
from pymavlink import mavutil

# Menambahkan path folder 'main' ke sys.path agar bisa membaca folder 'config'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
try:
    from config.main import PIXHAWK_PORT, PIXHAWK_BAUD, CAMERA_INDEX
    from web_dashboard import start_web_server, update_web_data
except ImportError:
    PIXHAWK_PORT = '/dev/ttyACM0'
    PIXHAWK_BAUD = 115200
    CAMERA_INDEX = 0

    # Fallback jika web_dashboard gagal diimport untuk alasan apapun
    def start_web_server(port=5000): pass
    def update_web_data(frame, telemetry): pass

# ================= KONFIGURASI =================
KP_XY = 0.0015            # Diperkecil agar gerakan tidak terlalu agresif (osilasi)
KP_Z = 0.5                # Proportional gain sumbu Z (Altitude)
MAX_SPEED = 0.3           # Kecepatan maksimal diturunkan agar lebih stabil
TARGET_ALTITUDE = 2.0     # Target ketinggian (meter)
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
    """
    Mengirimkan command pergerakan velocity pada frame BODY_NED.
    Kondisi drone WAJIB dalam mode GUIDED.
    """
    master.mav.set_position_target_local_ned_send(
        0, master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_BODY_NED,
        0b0000111111000111,
        0, 0, 0, vx, vy, vz, 0, 0, 0, 0, 0
    )

def main():
    parser = argparse.ArgumentParser(description='Test Centering Marker 7x7')
    parser.add_argument('--connect', default=PIXHAWK_PORT, help="Port Pixhawk")
    parser.add_argument('--baud', type=int, default=PIXHAWK_BAUD, help="Baudrate Pixhawk")
    parser.add_argument('--camera', type=int, default=CAMERA_INDEX, help="Index kamera")
    args = parser.parse_args()

    # Koneksi ke Pixhawk
    master = connect_pixhawk(args.connect, args.baud)

    # Inisialisasi Kamera
    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("❌ Gagal membuka kamera.")
        return

    # Inisialisasi ArUco Dictionary untuk 7x7
    # Note: Bisa menggunakan DICT_7X7_50, DICT_7X7_100, dst. sesuai yang dicetak
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_7X7_1000)
    aruco_params = cv2.aruco.DetectorParameters()
    try:
        aruco_params.minMarkerPerimeterRate = 0.03
    except:
        pass

    has_new_api = hasattr(cv2.aruco, 'ArucoDetector')
    if has_new_api:
        detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    print("\n🚀 Memulai Program Centering Marker 7x7!")
    print("⚠️ PASTIKAN DRONE DALAM MODE GUIDED AGAR COMMAND PERGERAKAN BERJALAN ⚠️")

    # Mulai Web Server di port 5000
    start_web_server(port=5000)

    current_alt = None

    try:
        while True:
            # Baca data ketinggian terbaru dari Pixhawk
            while True:
                msg = master.recv_match(type=['GLOBAL_POSITION_INT', 'LOCAL_POSITION_NED', 'RANGEFINDER'], blocking=False)
                if not msg:
                    break
                
                msg_type = msg.get_type()
                if msg_type == 'GLOBAL_POSITION_INT':
                    current_alt = msg.relative_alt / 1000.0  # Konversi mm ke meter
                elif msg_type == 'LOCAL_POSITION_NED':
                    current_alt = -msg.z  # NED frame: Z negatif artinya naik
                elif msg_type == 'RANGEFINDER':
                    current_alt = msg.distance  # Jarak dari lidar/sonar ke tanah

            # Hitung vz untuk menjaga ketinggian 2 meter
            # vz negatif = naik, vz positif = turun
            if current_alt is not None:
                error_alt = TARGET_ALTITUDE - current_alt
                target_vz = np.clip(-1.0 * error_alt * KP_Z, -MAX_SPEED, MAX_SPEED)
            else:
                target_vz = 0.0  # Jangan bergerak vertikal jika tidak ada data ketinggian

            ret, frame = cap.read()
            if not ret:
                break
    
            h, w, _ = frame.shape
            center_x_frame = w // 2
            center_y_frame = h // 2
    
            # Gambar crosshair (titik tengah frame)
            cv2.line(frame, (center_x_frame - 15, center_y_frame), (center_x_frame + 15, center_y_frame), (255, 0, 0), 2)
            cv2.line(frame, (center_x_frame, center_y_frame - 15), (center_x_frame, center_y_frame + 15), (255, 0, 0), 2)
    
            # Deteksi Marker ArUco 7x7
            if has_new_api:
                corners, ids, rejected = detector.detectMarkers(frame)
            else:
                corners, ids, rejected = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=aruco_params)
    
            if ids is not None and len(ids) > 0:
                # Ambil marker pertama yang dideteksi
                points = corners[0][0]
                cx = int(np.mean(points[:, 0]))
                cy = int(np.mean(points[:, 1]))
                
                # Gambar visualisasi marker
                cv2.aruco.drawDetectedMarkers(frame, corners, ids)
                cv2.line(frame, (center_x_frame, center_y_frame), (cx, cy), (0, 255, 255), 2)
    
                # Hitung error titik tengah
                error_x = cx - center_x_frame
                error_y = cy - center_y_frame
    
                # P-Controller: konversi error (pixel) menjadi velocity (m/s)
                # Pada frame BODY_NED: Sumbu X adalah Maju/Mundur, Sumbu Y adalah Kanan/Kiri
                # Pada kamera (menghadap ke bawah): error_y negatif berarti marker di atas (harus maju -> X positif)
                # error_x positif berarti marker di kanan (harus ke kanan -> Y positif)
                target_vx = np.clip(-1.0 * error_y * KP_XY, -MAX_SPEED, MAX_SPEED)
                target_vy = np.clip(1.0 * error_x * KP_XY, -MAX_SPEED, MAX_SPEED)
                
                # Kirim data pergerakan (Termasuk koreksi altitude di VZ)
                send_velocity(master, target_vx, target_vy, target_vz)
    
                status_text = f"CENTERING | vx: {target_vx:.2f} vy: {target_vy:.2f} vz: {target_vz:.2f}"
                cv2.putText(frame, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # Indikator jika sudah center (toleransi 40 pixel)
                if abs(error_x) < 40 and abs(error_y) < 40:
                    cv2.putText(frame, "TARGET TERKUNCI", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                    is_centered = True
                else:
                    is_centered = False
    
                # Siapkan data telemetri untuk web
                telem_data = {
                    "Status": "MENGARAH KE TARGET" if not is_centered else "TARGET TERKUNCI",
                    "Altitude (m)": f"{current_alt:.2f}" if current_alt is not None else "Unknown",
                    "Error X (px)": f"{error_x}",
                    "Error Y (px)": f"{error_y}",
                    "Velocity X": f"{target_vx:.2f} m/s",
                    "Velocity Y": f"{target_vy:.2f} m/s",
                    "Velocity Z": f"{target_vz:.2f} m/s"
                }
    
            else:
                # Marker tidak terdeteksi, berhenti sepenuhnya (hover)
                send_velocity(master, 0.0, 0.0, 0.0)
                cv2.putText(frame, "MENCARI MARKER 7x7", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                # Siapkan data telemetri pencarian
                telem_data = {
                    "Status": "MENCARI MARKER 7x7",
                    "Altitude (m)": f"{current_alt:.2f}" if current_alt is not None else "Unknown",
                    "Error X (px)": "N/A",
                    "Error Y (px)": "N/A",
                    "Velocity X": "0.00 m/s",
                    "Velocity Y": "0.00 m/s",
                    "Velocity Z": "0.00 m/s"
                }
    
            # Update data ke web dashboard
            update_web_data(frame, telem_data)
    
            # Kirim Heartbeat secara kontinu agar koneksi GCS tidak time-out
            master.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS,
                mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0
        )

    except KeyboardInterrupt:
        print("\n🛑 Program dihentikan oleh user (Ctrl+C).")
    finally:
        cap.release()

if __name__ == '__main__':
    main()
