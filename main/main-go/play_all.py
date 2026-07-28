#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script untuk menjalankan seluruh segmen misi secara otomatis dari WP1 hingga WP5.
"""

import subprocess
import os
import time
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
scripts = [
    "wp1-wp2.py",
    "wp2-wp3.py",
    "wp3-wp4.py",
    "wp4-wp5.py"
]

def main():
    print("🚀 Memulai eksekusi seluruh segmen misi secara berurutan...")
    for script in scripts:
        print(f"\n======================================")
        print(f"▶ MENJALANKAN SEGMEN: {script}")
        print(f"======================================\n")
        
        script_path = os.path.join(BASE_DIR, script)
        if not os.path.exists(script_path):
            print(f"❌ Script {script} tidak ditemukan!")
            break

        # Jalankan script menggunakan python
        process = subprocess.Popen([sys.executable, script_path])
        
        # Tunggu sampai script selesai (berjalan sukses atau abort)
        process.wait()
        
        if process.returncode != 0:
            print(f"❌ Segmen {script} berhenti dengan error (Exit Code: {process.returncode}).")
            print("🛑 Menghentikan antrian misi selanjutnya demi keamanan.")
            break
            
        print(f"✅ Segmen {script} berhasil diselesaikan. Menyiapkan segmen berikutnya...")
        time.sleep(3)  # Jeda 3 detik agar Pixhawk stabil sebelum perintah berikutnya
        
    print("\n🏁 SEMUA SEGMEN MISI DALAM ANTRIAN TELAH SELESAI.")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Eksekusi dibatalkan oleh pengguna.")
