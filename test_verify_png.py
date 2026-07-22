#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script verifikasi file PNG marker ArUco yang sudah di-generate.
Langsung membaca file PNG dari disk dan mendeteksi marker di dalamnya
TANPA memerlukan kamera.
Jika ID muncul -> file PNG valid dan bisa digunakan.
"""

import sys
import os
import cv2
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Folder tempat file PNG disimpan (folder yang sama dengan script ini)
TEST_DIR = os.path.dirname(os.path.abspath(__file__))

# File PNG yang akan diuji
PNG_FILES = {
    "WP1 (ID 1)": "wp1_aruco_id1.png",
    "WP2 (ID 2)": "wp2_aruco_id2.png",
    "WP3 (ID 3)": "wp3_aruco_id3.png",
    "WP4 (ID 4)": "wp4_aruco_id4.png",
}

# Semua kamus yang akan dicoba
DICTS_TO_TRY = {
    "DICT_7X7_50":   cv2.aruco.DICT_7X7_50,
    "DICT_7X7_100":  cv2.aruco.DICT_7X7_100,
    "DICT_7X7_250":  cv2.aruco.DICT_7X7_250,
    "DICT_7X7_1000": cv2.aruco.DICT_7X7_1000,
    "DICT_ORIGINAL": cv2.aruco.DICT_ARUCO_ORIGINAL,
    "DICT_4X4_50":   cv2.aruco.DICT_4X4_50,
    "DICT_5X5_50":   cv2.aruco.DICT_5X5_50,
    "DICT_6X6_50":   cv2.aruco.DICT_6X6_50,
}

has_new_api = hasattr(cv2.aruco, 'ArucoDetector')

def detect_in_image(img, dict_name, dict_type):
    """Deteksi ArUco marker dalam sebuah gambar menggunakan kamus tertentu."""
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_type)
    params     = cv2.aruco.DetectorParameters()
    try:
        params.minMarkerPerimeterRate = 0.01
    except:
        pass

    if has_new_api:
        det = cv2.aruco.ArucoDetector(aruco_dict, params)
        corners, ids, _ = det.detectMarkers(img)
    else:
        corners, ids, _ = cv2.aruco.detectMarkers(img, aruco_dict, parameters=params)

    if ids is not None and len(ids) > 0:
        return [int(i) for i in ids.flatten()]
    return []

def main():
    print("=" * 60)
    print("  VERIFIKASI FILE PNG ARUCO MARKER")
    print("=" * 60)

    for wp_name, filename in PNG_FILES.items():
        filepath = os.path.join(TEST_DIR, filename)
        print(f"\n--- {wp_name} ---")
        print(f"  File : {filename}")

        if not os.path.exists(filepath):
            print(f"  [TIDAK ADA] File tidak ditemukan: {filepath}")
            continue

        # Baca gambar dari disk
        img = cv2.imread(filepath, cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(f"  [ERROR] Gagal membaca file gambar.")
            continue

        print(f"  Ukuran: {img.shape[1]}x{img.shape[0]} px")

        found_any = False
        for dict_name, dict_type in DICTS_TO_TRY.items():
            detected_ids = detect_in_image(img, dict_name, dict_type)
            if detected_ids:
                print(f"  [TERDETEKSI] Kamus={dict_name} -> ID={detected_ids}")
                found_any = True

        if not found_any:
            print(f"  [GAGAL] Tidak terdeteksi oleh kamus manapun!")
            print(f"          -> File mungkin rusak atau format tidak didukung.")

    print("\n" + "=" * 60)
    print("Selesai. Bagikan hasil di atas untuk troubleshooting lebih lanjut.")
    print("=" * 60)

if __name__ == '__main__':
    main()
