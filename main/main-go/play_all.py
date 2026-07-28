#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script untuk menjalankan seluruh segmen misi secara otomatis dari WP1 hingga WP5.
"""

import subprocess
import os
import time
import sys
import signal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
scripts = [
    "wp1-wp2.py",
    "wp2-wp3.py",
    "wp3-wp4.py",
    "wp4-wp5.py"
]

current_process = None

def signal_handler(signum, frame):
    global current_process
    print("\n🛑 Menerima sinyal terminasi. Menghentikan segmen yang sedang berjalan...")
    if current_process is not None:
        try:
            current_process.terminate()
            current_process.wait(timeout=2)
        except Exception:
            pass
    sys.exit(0)

# Pasang handler untuk SIGTERM dan SIGINT agar anak proses (wp scripts) juga ikut mati
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def main():
    global current_process
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
        current_process = subprocess.Popen([sys.executable, script_path])
        
        # Tunggu sampai script selesai (berjalan sukses atau abort)
        current_process.wait()
        
        if current_process.returncode != 0:
            print(f"❌ Segmen {script} berhenti dengan error (Exit Code: {current_process.returncode}).")
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
