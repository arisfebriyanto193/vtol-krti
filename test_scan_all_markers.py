#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script Diagnostik Sederhana:
Mendeteksi SEMUA ArUco Marker yang terlihat kamera tanpa filter ID apapun.
Gunakan ini untuk memverifikasi bahwa gambar marker WP1, WP2, WP3, WP4
bisa terbaca kamera sebelum menjalankan program otonom.

CARA PAKAI:
  python test_scan_all_markers.py --camera 1
  Lalu tunjukkan gambar wp1_aruco_id1.png, wp2_aruco_id2.png, dst. ke kamera.
  Jika ID muncul di layar, marker tersebut berhasil dibaca kamera.
"""

import sys
import cv2
import argparse
import numpy as np

# Force UTF-8 di terminal Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ===== KONFIGURASI =====
# Ganti ke DICT_7X7_1000 jika marker dicetak menggunakan kamus yang berbeda
ARUCO_DICT_TYPE = cv2.aruco.DICT_7X7_50
LOCK_TOLERANCE  = 50  # Radius lingkaran toleransi center (pixel)
# =======================

def main():
    parser = argparse.ArgumentParser(description='Scan semua ArUco Marker (tanpa filter ID)')
    parser.add_argument('--camera', type=int, default=1, help='Index kamera (default: 1)')
    args = parser.parse_args()

    # Buka kamera
    if sys.platform == 'win32':
        cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(args.camera)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print(f"[ERROR] Gagal membuka kamera index {args.camera}.")
        print("Coba ganti --camera 0 atau --camera 2")
        return

    # Inisialisasi Detektor ArUco
    aruco_dict   = cv2.aruco.getPredefinedDictionary(ARUCO_DICT_TYPE)
    aruco_params = cv2.aruco.DetectorParameters()
    try:
        aruco_params.minMarkerPerimeterRate = 0.02  # Lebih sensitif agar bisa terbaca dari jauh
    except:
        pass

    has_new_api = hasattr(cv2.aruco, 'ArucoDetector')
    if has_new_api:
        detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    print("\n[START] Scanner Diagnostik ArUco - Mendeteksi SEMUA ID")
    print(f"        Kamus yang digunakan : DICT_7X7_50")
    print(f"        Kamera Index         : {args.camera}")
    print("        Tekan 'Q' di jendela kamera untuk keluar.\n")

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("[WARNING] Gagal membaca frame kamera!")
            break

        h, w = frame.shape[:2]
        cx_frame = w // 2
        cy_frame = h // 2

        # Deteksi semua marker di frame
        if has_new_api:
            corners, ids, rejected = detector.detectMarkers(frame)
        else:
            corners, ids, rejected = cv2.aruco.detectMarkers(
                frame, aruco_dict, parameters=aruco_params)

        # Gambar crosshair
        cv2.line(frame, (cx_frame - 20, cy_frame), (cx_frame + 20, cy_frame), (255, 0, 0), 2)
        cv2.line(frame, (cx_frame, cy_frame - 20), (cx_frame, cy_frame + 20), (255, 0, 0), 2)
        cv2.circle(frame, (cx_frame, cy_frame), LOCK_TOLERANCE, (80, 80, 80), 1)

        if ids is not None and len(ids) > 0:
            # Gambar kotak deteksi untuk SEMUA marker yang terlihat
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)

            for i, marker_id in enumerate(ids.flatten()):
                pts    = corners[i][0]
                cx     = int(np.mean(pts[:, 0]))
                cy     = int(np.mean(pts[:, 1]))
                err_x  = cx - cx_frame
                err_y  = cy - cy_frame
                locked = abs(err_x) < LOCK_TOLERANCE and abs(err_y) < LOCK_TOLERANCE

                color  = (0, 255, 0) if locked else (0, 165, 255)

                # Gambar titik tengah dan garis ke crosshair
                cv2.circle(frame, (cx, cy), 6, color, -1)
                cv2.line(frame, (cx_frame, cy_frame), (cx, cy), (0, 255, 255), 1)

                # Label di atas marker
                label      = f"ID: {marker_id}  WP: {marker_id}"
                lock_label = " [LOCKED]" if locked else ""
                cv2.putText(frame, label + lock_label,
                            (cx - 10, cy - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                # Print ke terminal
                print(f"[DETECTED] ID:{marker_id} | X:{cx} Y:{cy} | dX:{err_x:+d} dY:{err_y:+d} | {'LOCKED' if locked else 'TRACKING'}")

            # Panel info
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (380, 60 + 25 * len(ids)), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

            cv2.putText(frame, f"TERDETEKSI: {len(ids)} MARKER", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            id_list = ', '.join([f'ID {i}' for i in ids.flatten()])
            cv2.putText(frame, f"ID LIST : {id_list}", (10, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        else:
            # Panel info - tidak ada marker
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (380, 60), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

            cv2.putText(frame, "TIDAK ADA MARKER", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.putText(frame, "Tunjukkan gambar ArUco ke kamera", (10, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 100, 255), 1)

        cv2.imshow("Diagnostik Scanner ArUco - Semua ID", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
