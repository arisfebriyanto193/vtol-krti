#!/usr/bin/env python3
import os
import sys
import cv2
import time
import argparse
import numpy as np

# Menambahkan path folder 'main' ke sys.path agar bisa membaca folder 'config'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
try:
    from config.main import CAMERA_INDEX
    from web_dashboard import start_web_server, update_web_data
except ImportError:
    CAMERA_INDEX = 0
    # Fallback
    def start_web_server(port=5000): pass
    def update_web_data(frame, telemetry): pass

# ================= KONFIGURASI SIMULASI =================
KP_XY = 0.005             # Gain simulasi
# ========================================================

def main():
    parser = argparse.ArgumentParser(description='Cek Orientasi Kamera Marker 7x7 (Tanpa Pixhawk)')
    parser.add_argument('--camera', type=int, default=CAMERA_INDEX, help="Index kamera")
    args = parser.parse_args()

    # Inisialisasi Kamera
    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("❌ Gagal membuka kamera.")
        return

    # Inisialisasi ArUco Dictionary untuk 7x7
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_7X7_1000)
    aruco_params = cv2.aruco.DetectorParameters()
    try:
        aruco_params.minMarkerPerimeterRate = 0.03
    except:
        pass

    has_new_api = hasattr(cv2.aruco, 'ArucoDetector')
    if has_new_api:
        detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    print("\n🚀 Memulai Uji Orientasi Kamera (TANPA PIXHAWK)!")
    print("🌍 Buka Web Dashboard di http://0.0.0.0:5000")
    print("Tekan Ctrl+C untuk berhenti.")

    # Mulai Web Server di port 5000
    start_web_server(port=5000)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
    
            h, w, _ = frame.shape
            center_x_frame = w // 2
            center_y_frame = h // 2
    
            # Gambar crosshair (titik tengah frame)
            cv2.line(frame, (center_x_frame - 15, center_y_frame), (center_x_frame + 15, center_y_frame), (255, 255, 255), 2)
            cv2.line(frame, (center_x_frame, center_y_frame - 15), (center_x_frame, center_y_frame + 15), (255, 255, 255), 2)
            
            # Tambahkan teks penunjuk orientasi layar
            cv2.putText(frame, "DEPAN DRONE (X+)", (center_x_frame - 70, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, "KANAN (Y+)", (w - 100, center_y_frame), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
            # Deteksi Marker ArUco 7x7
            if has_new_api:
                corners, ids, rejected = detector.detectMarkers(frame)
            else:
                corners, ids, rejected = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=aruco_params)
    
            if ids is not None and len(ids) > 0:
                points = corners[0][0]
                cx = int(np.mean(points[:, 0]))
                cy = int(np.mean(points[:, 1]))
                
                # Gambar visualisasi marker
                cv2.aruco.drawDetectedMarkers(frame, corners, ids)
                # Garis dari tengah frame ke marker
                cv2.line(frame, (center_x_frame, center_y_frame), (cx, cy), (0, 255, 255), 2)
    
                # Hitung error
                error_x = cx - center_x_frame
                error_y = cy - center_y_frame
    
                # Simulasi Kecepatan (Tanpa dikirim ke Pixhawk)
                # Target VX (Maju) akan Positif jika marker ada di atas tengah layar (error_y negatif)
                # Target VY (Kanan) akan Positif jika marker ada di kanan layar (error_x positif)
                target_vx = -1.0 * error_y * KP_XY
                target_vy = 1.0 * error_x * KP_XY
                
                # Gambar arah pergerakan SEHARUSNYA (Panah Merah)
                # target_vx positif = harus bergerak maju (ke atas di gambar)
                # target_vy positif = harus bergerak ke kanan (ke kanan di gambar)
                arrow_scale = 100  # Skala untuk memperbesar panah
                arrow_end_x = int(center_x_frame + (target_vy * arrow_scale))
                arrow_end_y = int(center_y_frame - (target_vx * arrow_scale))  # Y di opencv ke bawah positif, jadi dikurang agar panah ke atas jika maju
                
                cv2.arrowedLine(frame, (center_x_frame, center_y_frame), (arrow_end_x, arrow_end_y), (0, 0, 255), 4, tipLength=0.2)
                cv2.putText(frame, "ARAH PERGERAKAN DRONE", (arrow_end_x + 10, arrow_end_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                
                # Teks informasi
                status_text = f"SIMULASI | vx: {target_vx:.2f} vy: {target_vy:.2f}"
                cv2.putText(frame, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
                telem_data = {
                    "Status": "MENDETEKSI MARKER",
                    "Arah Pergerakan": "Maju" if target_vx > 0 else "Mundur",
                    "Error X (px)": f"{error_x}",
                    "Error Y (px)": f"{error_y}",
                    "Simulasi VX": f"{target_vx:.2f} m/s",
                    "Simulasi VY": f"{target_vy:.2f} m/s"
                }
    
            else:
                cv2.putText(frame, "MENCARI MARKER 7x7", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                telem_data = {
                    "Status": "MENCARI MARKER",
                    "Arah Pergerakan": "DIAM (HOVER)",
                    "Error X (px)": "N/A",
                    "Error Y (px)": "N/A",
                    "Simulasi VX": "0.00 m/s",
                    "Simulasi VY": "0.00 m/s"
                }
    
            # Update data ke web dashboard
            update_web_data(frame, telem_data)
            
            # Tidur sebentar agar tidak membebani CPU (opsional karena cap.read() sudah memblokir)
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n🛑 Simulasi dihentikan oleh user (Ctrl+C).")
    finally:
        cap.release()

if __name__ == '__main__':
    main()
