#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script Diagnostik Multi-Dictionary:
Mencoba SEMUA kamus ArUco 7x7 secara bersamaan untuk mengetahui kamus mana
yang cocok dengan marker fisik Anda.
Tekan 'Q' untuk keluar.
"""

import sys
import cv2
import argparse
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Daftar kamus yang akan dicoba sekaligus
DICTS_TO_TRY = {
    "7X7_50":   cv2.aruco.DICT_7X7_50,
    "7X7_100":  cv2.aruco.DICT_7X7_100,
    "7X7_250":  cv2.aruco.DICT_7X7_250,
    "7X7_1000": cv2.aruco.DICT_7X7_1000,
    "ORIGINAL": cv2.aruco.DICT_ARUCO_ORIGINAL,
    "4X4_50":   cv2.aruco.DICT_4X4_50,
    "5X5_50":   cv2.aruco.DICT_5X5_50,
    "6X6_50":   cv2.aruco.DICT_6X6_50,
}

# Warna berbeda untuk tiap kamus agar mudah dibedakan di layar
DICT_COLORS = {
    "7X7_50":   (0, 255, 0),
    "7X7_100":  (0, 200, 255),
    "7X7_250":  (255, 200, 0),
    "7X7_1000": (255, 0, 200),
    "ORIGINAL": (0, 0, 255),
    "4X4_50":   (200, 100, 0),
    "5X5_50":   (0, 255, 200),
    "6X6_50":   (100, 0, 255),
}

def main():
    parser = argparse.ArgumentParser(description='Multi-Dictionary ArUco Scanner')
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
        print(f"[ERROR] Gagal membuka kamera index {args.camera}. Coba --camera 0 atau 2")
        return

    # Siapkan semua detektor
    detectors = {}
    has_new_api = hasattr(cv2.aruco, 'ArucoDetector')
    for name, dict_id in DICTS_TO_TRY.items():
        d = cv2.aruco.getPredefinedDictionary(dict_id)
        p = cv2.aruco.DetectorParameters()
        try:
            p.minMarkerPerimeterRate = 0.02
        except:
            pass
        if has_new_api:
            detectors[name] = cv2.aruco.ArucoDetector(d, p)
        else:
            detectors[name] = (d, p)

    print("\n[MULTI-DICT SCANNER] Mencoba semua kamus ArUco 7x7 secara bersamaan...")
    print("Tunjukkan marker ke kamera. Kamus yang mendeteksi akan muncul di layar & terminal.")
    print("Tekan 'Q' untuk keluar.\n")

    last_detected = {}  # {dict_name: (id, timestamp)}

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        h, w = frame.shape[:2]
        cx_f, cy_f = w // 2, h // 2
        display = frame.copy()

        # Gambar crosshair
        cv2.line(display, (cx_f - 20, cy_f), (cx_f + 20, cy_f), (255, 0, 0), 2)
        cv2.line(display, (cx_f, cy_f - 20), (cx_f, cy_f + 20), (255, 0, 0), 2)

        detected_summary = []

        for name, det in detectors.items():
            try:
                if has_new_api:
                    corners, ids, _ = det.detectMarkers(frame)
                else:
                    d_obj, p_obj = det
                    corners, ids, _ = cv2.aruco.detectMarkers(frame, d_obj, parameters=p_obj)
            except:
                continue

            if ids is not None and len(ids) > 0:
                color = DICT_COLORS[name]
                for i, mid in enumerate(ids.flatten()):
                    pts = corners[i][0]
                    cx = int(np.mean(pts[:, 0]))
                    cy = int(np.mean(pts[:, 1]))

                    # Gambar kotak marker dengan warna berbeda per kamus
                    cv2.polylines(display, [pts.astype(np.int32)], True, color, 3)
                    cv2.circle(display, (cx, cy), 5, color, -1)

                    label = f"{name}:ID{mid}"
                    cv2.putText(display, label, (cx - 10, cy - 12),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

                    detected_summary.append(f"[{name}] ID:{mid}")

                    # Print ke terminal hanya jika baru (menghindari spam)
                    key_str = f"{name}_{mid}"
                    if key_str not in last_detected:
                        print(f"[DETECTED] Kamus={name} | ID={mid} | X={cx} Y={cy}")
                    last_detected[key_str] = True

        # Bersihkan cache jika tidak ada deteksi
        if not detected_summary:
            last_detected.clear()

        # Panel ringkasan di kiri atas
        panel_h = 30 + 22 * max(len(detected_summary), 1)
        overlay = display.copy()
        cv2.rectangle(overlay, (0, 0), (400, panel_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, display, 0.45, 0, display)

        if detected_summary:
            cv2.putText(display, f"TERDETEKSI: {len(detected_summary)} MARKER", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
            for i, s in enumerate(detected_summary):
                cv2.putText(display, s, (8, 44 + i * 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        else:
            cv2.putText(display, "Tidak ada marker terdeteksi", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
            cv2.putText(display, "Tunjukkan gambar ArUco ke kamera", (8, 44),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 255), 1)

        cv2.putText(display, "Multi-Dict Scanner | Q=Keluar", (w - 280, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1)

        cv2.imshow("Multi-Dictionary ArUco Scanner", display)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
