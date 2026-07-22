#!/usr/bin/env python3
import os
import sys
import cv2
import numpy as np

# Force UTF-8 di terminal Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Menambahkan path folder 'main' ke sys.path agar bisa membaca folder 'config'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from config.main import CAMERA_INDEX

def main():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    # TINGKATKAN RESOLUSI KE 720p AGAR KOTAK 7x7 YANG KECIL BISA TERBACA JELAS
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    if not cap.isOpened():
        print("❌ Gagal membuka kamera.")
        return

    # Kembalikan ke 7X7_50 sesuai konfirmasi Anda
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_7X7_50)
    aruco_params = cv2.aruco.DetectorParameters()
    
    # PERBAIKAN PARAMETER DETEKSI UNTUK KAMERA BURAM / KONTRAS RENDAH
    try:
        # Sedikit menurunkan batas ukuran minimum marker agar bisa terbaca dari jauh
        aruco_params.minMarkerPerimeterRate = 0.01
    except:
        pass
    
    has_new_api = hasattr(cv2.aruco, 'ArucoDetector')
    if has_new_api:
        detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    print("\n🚀 Memulai Scanner ArUco 7X7 (High Resolution)")
    print("Tekan tombol 'q' untuk keluar.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        h, w, _ = frame.shape
        center_x_frame = w // 2
        center_y_frame = h // 2
        
        cv2.line(frame, (center_x_frame - 15, center_y_frame), (center_x_frame + 15, center_y_frame), (255, 0, 0), 2)
        cv2.line(frame, (center_x_frame, center_y_frame - 15), (center_x_frame, center_y_frame + 15), (255, 0, 0), 2)

        if has_new_api:
            corners, ids, rejected = detector.detectMarkers(frame)
        else:
            corners, ids, rejected = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=aruco_params)

        # GAMBAR KOTAK MERAH UNTUK MARKER YANG DITOLAK (REJECTED)
        if rejected is not None and len(rejected) > 0:
            cv2.aruco.drawDetectedMarkers(frame, rejected, borderColor=(0, 0, 255))
            cv2.putText(frame, f"REJECTED: {len(rejected)} squares", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        if ids is not None and len(ids) > 0:
            points = corners[0][0]
            qr_center_x = int(np.mean(points[:, 0]))
            qr_center_y = int(np.mean(points[:, 1]))

            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
            cv2.circle(frame, (qr_center_x, qr_center_y), 5, (0, 0, 255), -1)
            cv2.line(frame, (center_x_frame, center_y_frame), (qr_center_x, qr_center_y), (0, 255, 255), 2)
            
            error_x_pixel = qr_center_x - center_x_frame
            error_y_pixel = qr_center_y - center_y_frame
            
            cv2.putText(frame, f"ID: {int(ids.flatten()[0])} | TYPE: ORIGINAL", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(frame, f"OFFSET X: {error_x_pixel} px | Y: {error_y_pixel} px", 
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(frame, "STATUS: TRACKING", (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        else:
            cv2.putText(frame, "MARKER TIDAK DITEMUKAN", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        cv2.imshow("Scanner ArUco Test", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
