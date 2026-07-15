#!/usr/bin/env python3
"""
Integrasi Kamera & Pixhawk (Pymavlink) untuk Mendeteksi QR Code 
dan Hover Tepat di Atasnya pada ketinggian 1.5 Meter.

Dependensi yang dibutuhkan:
pip3 install pymavlink opencv-python numpy
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
    
    # Request aliran data telemetri dengan frekuensi 5Hz
    master.mav.request_data_stream_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1
    )
    return master

def send_velocity(master, vx, vy, vz):
    """
    Kirim kecepatan ke Pixhawk dalam frame BODY_NED (relatif terhadap kepala drone).
    vx: Kecepatan maju/mundur (m/s, positif = maju)
    vy: Kecepatan kanan/kiri (m/s, positif = kanan)
    vz: Kecepatan atas/bawah (m/s, positif = turun, negatif = naik)
    """
    master.mav.set_position_target_local_ned_send(
        0,       # time_boot_ms (tidak dipakai)
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_BODY_NED,
        0b0000111111000111, # type_mask: abaikan posisi & percepatan, gunakan kecepatan
        0, 0, 0,    # posisi x, y, z (diabaikan)
        vx, vy, vz, # target kecepatan vx, vy, vz
        0, 0, 0,    # percepatan (diabaikan)
        0, 0        # yaw, yaw_rate (diabaikan)
    )

def get_altitude(master, current_alt):
    """Membaca ketinggian relatif dari Pixhawk jika ada pesan yang masuk."""
    msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=False)
    if msg:
        return msg.relative_alt / 1000.0 # konversi dari mm ke meter
    return current_alt

def main():
    parser = argparse.ArgumentParser(description='Dual Gate QR Center PID Hovering')
    parser.add_argument('--connect', default='/dev/ttyACM0', help="Port Pixhawk (contoh: /dev/ttyACM0)")
    parser.add_argument('--baud', type=int, default=115200, help="Baudrate Pixhawk")
    parser.add_argument('--camera', type=int, default=0, help="Index kamera")
    args = parser.parse_args()

    # Inisialisasi koneksi Pixhawk
    master = connect_pixhawk(args.connect, args.baud)
    
    # Inisialisasi Kamera
    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    if not cap.isOpened():
        print(f"❌ Gagal membuka kamera dengan index {args.camera}")
        return

    qr_decoder = cv2.QRCodeDetector()
    current_alt = 0.0

    print("\n🚀 Sistem Siap!")
    print("Bawa drone terbang, pindahkan ke mode GUIDED, dan drone akan mulai menengahkan QR otomatis.")
    print("Tekan tombol 'q' pada jendela video untuk keluar.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Gagal membaca frame dari kamera.")
            break
            
        h, w, _ = frame.shape
        center_x_frame = w // 2
        center_y_frame = h // 2
        
        # Update ketinggian dari telemetri
        current_alt = get_altitude(master, current_alt)

        # Gambar tanda silang (titik tengah drone)
        cv2.line(frame, (center_x_frame - 10, center_y_frame), (center_x_frame + 10, center_y_frame), (255, 0, 0), 2)
        cv2.line(frame, (center_x_frame, center_y_frame - 10), (center_x_frame, center_y_frame + 10), (255, 0, 0), 2)

        # Deteksi QR Code
        data, bbox, _ = qr_decoder.detectAndDecode(frame)

        if bbox is not None and len(bbox) > 0:
            points = bbox[0]
            
            # Hitung kordinat tengah QR Code
            qr_center_x = int(np.mean([p[0] for p in points]))
            qr_center_y = int(np.mean([p[1] for p in points]))

            # Menggambar bounding box QR Code
            for i in range(len(points)):
                pt1 = tuple(points[i].astype(int))
                pt2 = tuple(points[(i+1)%4].astype(int))
                cv2.line(frame, pt1, pt2, (0, 255, 0), 2)
                
            # Menggambar garis target dari tengah drone ke QR
            cv2.circle(frame, (qr_center_x, qr_center_y), 5, (0, 0, 255), -1)
            cv2.line(frame, (center_x_frame, center_y_frame), (qr_center_x, qr_center_y), (0, 255, 255), 2)
            
            # ================= LOGIKA KENDALI PID =================
            # Asumsi orientasi kamera:
            # Sumbu Y kamera (atas-bawah layar) -> Pitch (Gerak maju/mundur drone / sumbu X)
            # Sumbu X kamera (kiri-kanan layar) -> Roll (Gerak kanan/kiri drone / sumbu Y)
            # *Ini mungkin butuh kamu sesuaikan jika posisi masang kamera dibalik*
            
            error_x_pixel = qr_center_x - center_x_frame
            error_y_pixel = qr_center_y - center_y_frame
            
            # Jika QR Code berada di bawah layar kamera (nilai Y positif), drone perlu mundur (-X Velocity)
            target_vx = -1.0 * error_y_pixel * KP_XY
            
            # Jika QR Code berada di kanan layar (nilai X positif), drone perlu ke kanan (+Y Velocity)
            target_vy = 1.0 * error_x_pixel * KP_XY
            
            # Kendali Ketinggian (Altitude)
            error_alt = TARGET_ALTITUDE - current_alt
            # VZ (Sumbu Z MAVLink): Nilai Positif berarti Turun, Nilai Negatif berarti Naik
            target_vz = -1.0 * error_alt * KP_Z
            
            # Clamping kecepatan supaya drone tidak bergerak terlalu agresif (berbahaya)
            target_vx = np.clip(target_vx, -MAX_SPEED, MAX_SPEED)
            target_vy = np.clip(target_vy, -MAX_SPEED, MAX_SPEED)
            target_vz = np.clip(target_vz, -MAX_SPEED, MAX_SPEED)
            
            # Kirim perintah pergerakan ke Pixhawk
            send_velocity(master, target_vx, target_vy, target_vz)

            # Tampilkan OSD
            cv2.putText(frame, f"VZ: {target_vz:.2f} | VX: {target_vx:.2f} | VY: {target_vy:.2f}", 
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(frame, f"Alt: {current_alt:.2f}m / Target: 1.5m", 
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(frame, "STATUS: TRACKING QR", (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        else:
            # JIKA QR TIDAK TERDETEKSI
            # Tetap jaga ketinggian, tetapi hover (tidak ada pergerakan XY)
            error_alt = TARGET_ALTITUDE - current_alt
            target_vz = -1.0 * error_alt * KP_Z
            target_vz = np.clip(target_vz, -MAX_SPEED, MAX_SPEED)
            
            send_velocity(master, 0.0, 0.0, target_vz)
            
            cv2.putText(frame, "QR TIDAK DITEMUKAN - HOVERING", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.putText(frame, f"Alt: {current_alt:.2f}m / Target: 1.5m", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        cv2.imshow("Kamera Bawah - Auto QR Centering PID", frame)
        
        # Rutin kirim sinyal heartbeat balik sebagai GCS (Ground Control Station)
        master.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_GCS,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0
        )
        
        # Keluar loop jika 'q' ditekan
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Membersihkan kamera
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
