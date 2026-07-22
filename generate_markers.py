#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script untuk menghasilkan gambar ArUco Marker DICT_7X7_50
untuk WP1 (ID 1) s.d WP4 (ID 4) dengan border putih (quiet zone)
yang cukup agar marker bisa terdeteksi dengan benar.
"""

import os
import sys
import cv2
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Kamus ArUco yang sama dengan main_otonom_wp.py
ARUCO_DICT_TYPE = cv2.aruco.DICT_7X7_50

def generate_marker_with_border(aruco_dict, marker_id, marker_size=300, border_size=60):
    """
    Membuat gambar marker ArUco dengan border putih yang cukup.
    marker_size : ukuran kotak marker hitam-putih dalam piksel
    border_size : lebar border putih di sekeliling marker (quiet zone)
    """
    has_new_gen = hasattr(cv2.aruco, 'generateImageMarker')

    # Generate gambar marker dasar (tanpa border)
    if has_new_gen:
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_size)
    else:
        try:
            marker_img = cv2.aruco.drawMarker(aruco_dict, marker_id, marker_size)
        except Exception:
            marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_size)

    # Tambahkan border putih secara manual (quiet zone)
    total_size = marker_size + 2 * border_size
    canvas = np.ones((total_size, total_size), dtype=np.uint8) * 255  # Kanvas putih
    canvas[border_size:border_size + marker_size,
           border_size:border_size + marker_size] = marker_img

    return canvas

def main():
    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT_TYPE)
    output_dir = os.path.dirname(os.path.abspath(__file__))

    print("Menghasilkan ArUco Markers (DICT_7X7_50) dengan quiet zone...")
    print(f"Output folder: {output_dir}\n")

    has_new_gen = hasattr(cv2.aruco, 'generateImageMarker')
    print(f"OpenCV version : {cv2.__version__}")
    print(f"API baru (generateImageMarker): {has_new_gen}\n")

    for marker_id in [1, 2, 3, 4]:
        filename = os.path.join(output_dir, f"wp{marker_id}_aruco_id{marker_id}.png")

        # Generate dengan border putih 60px di semua sisi
        img = generate_marker_with_border(aruco_dict, marker_id,
                                          marker_size=300, border_size=60)

        # Simpan
        cv2.imwrite(filename, img)

        # Langsung verifikasi apakah file yang baru dibuat bisa terdeteksi
        params = cv2.aruco.DetectorParameters()
        try:
            params.minMarkerPerimeterRate = 0.01
        except:
            pass

        if hasattr(cv2.aruco, 'ArucoDetector'):
            det = cv2.aruco.ArucoDetector(aruco_dict, params)
            corners, ids, _ = det.detectMarkers(img)
        else:
            corners, ids, _ = cv2.aruco.detectMarkers(img, aruco_dict, parameters=params)

        if ids is not None and marker_id in ids.flatten():
            print(f"[OK] wp{marker_id}_aruco_id{marker_id}.png -> Terdeteksi sebagai ID {marker_id}")
        else:
            detected = ids.flatten().tolist() if ids is not None else []
            print(f"[GAGAL] wp{marker_id}_aruco_id{marker_id}.png -> Tidak terdeteksi! (IDs: {detected})")

    print("\nSelesai. Buka file PNG tersebut dan print atau tampilkan di layar untuk pengetesan.")

if __name__ == '__main__':
    main()
