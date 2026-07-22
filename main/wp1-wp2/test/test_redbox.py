#!/usr/bin/env python3
"""
Script Testing: Deteksi Box Merah & Simulasi Buka Servo
Program ini tidak akan menyalakan motor/mengirim kecepatan, HANYA menguji
apakah Box Merah terdeteksi dengan baik dan Servo berhasil terbuka.
"""

import cv2
import time
import argparse
import numpy as np
from pymavlink import mavutil

# ================= KONFIGURASI =================
PIXHAWK_MODE = False       # True = Hubung Pixhawk & Servo sungguhan | False = Hanya Visualisasi Layar
SERVO_PIN = 9             # Pin servo pada Pixhawk (AUX 1 biasanya pin 9)
SERVO_PWM_OPEN = 1900     # Nilai PWM untuk membuka servo / menjatuhkan barang
SERVO_PWM_CLOSE = 1100    # Nilai PWM standar/tertutup
# ===============================================

def connect_pixhawk(port, baudrate):
    print(f"Mencoba terhubung ke Pixhawk di {port} (Baudrate: {baudrate})...")
    try:
        master = mavutil.mavlink_connection(port, baud=baudrate)
        master.wait_heartbeat(timeout=3)
        if master.target_system == 0:
            print("⚠️ Pixhawk tidak merespon heartbeat, namun port terbuka.")
        else:
            print("✅ Berhasil Terhubung ke Pixhawk!")
        return master
    except Exception as e:
        print(f"❌ Gagal konek ke Pixhawk: {e}")
        print("TETAP MENJALANKAN SCRIPT HANYA UNTUK TEST KAMERA...")
        return None

def trigger_servo(master, pwm_value):
    if master is None:
        print(f"[SIMULASI SERVO] Mengirim PWM: {pwm_value}")
        return
        
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_SERVO, 0,
        SERVO_PIN, pwm_value, 0, 0, 0, 0, 0
    )

def detect_red_box(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Rentang warna merah dalam HSV (Merah ada di 2 rentang ujung hue)
    lower_red1 = np.array([0, 120, 70])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 120, 70])
    upper_red2 = np.array([180, 255, 255])
    
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = mask1 + mask2
    
    # Membersihkan noise
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if len(contours) > 0:
        c = max(contours, key=cv2.contourArea)
        if cv2.contourArea(c) > 1000: # Batas minimal ukuran box (dalam pixel)
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                x, y, w, h = cv2.boundingRect(c)
                return True, (cx, cy), (x, y, w, h)
    return False, (0, 0), (0, 0, 0, 0)

def main():
    parser = argparse.ArgumentParser(description='Test Deteksi Box Merah & Servo')
    parser.add_argument('--connect', default='/dev/ttyACM0', help="Port Pixhawk")
    parser.add_argument('--baud', type=int, default=115200, help="Baudrate Pixhawk")
    parser.add_argument('--camera', type=int, default=1, help="Index kamera")
    args = parser.parse_args()

    if PIXHAWK_MODE:
        master = connect_pixhawk(args.connect, args.baud)
    else:
        print("\n⚠️ PIXHAWK_MODE = False. Melewati koneksi Pixhawk, murni menggunakan Kamera!")
        master = None
    
    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    if not cap.isOpened():
        print(f"❌ Gagal membuka kamera.")
        return

    # Tutup servo (pengaman) di awal
    print("\n[INIT] Menutup Servo (PWM 1100)")
    trigger_servo(master, SERVO_PWM_CLOSE)

    stable_start_time = 0
    servo_terbuka = False
    
    print("\n🚀 Sistem Test Siap!")
    print("Arahkan kamera ke Box Merah dan paskan posisinya di tengah crosshair biru.")
    print("Tekan tombol 'q' untuk keluar atau tombol 'r' untuk reset servo.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        h, w, _ = frame.shape
        center_x_frame = w // 2
        center_y_frame = h // 2
        
        cv2.line(frame, (center_x_frame - 15, center_y_frame), (center_x_frame + 15, center_y_frame), (255, 0, 0), 2)
        cv2.line(frame, (center_x_frame, center_y_frame - 15), (center_x_frame, center_y_frame + 15), (255, 0, 0), 2)

        red_detected, red_center, red_box = detect_red_box(frame)
        
        if red_detected:
            cx, cy = red_center
            x, y, w, h_box = red_box
            cv2.rectangle(frame, (x, y), (x+w, y+h_box), (0, 255, 0), 3)
            cv2.line(frame, (center_x_frame, center_y_frame), (cx, cy), (0, 255, 255), 2)
            
            error_x = cx - center_x_frame
            error_y = cy - center_y_frame
            
            # Tampilkan nilai Error
            cv2.putText(frame, f"OFFSET X: {error_x} px | Y: {error_y} px", 
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # Cek apakah sudah sangat pas di tengah
            if abs(error_x) < 40 and abs(error_y) < 40 and not servo_terbuka:
                if stable_start_time == 0:
                    stable_start_time = time.time()
                
                waktu_tunggu = time.time() - stable_start_time
                cv2.putText(frame, f"MENGUNCI TARGET... {waktu_tunggu:.1f}s / 3.0s", 
                            (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                
                if waktu_tunggu > 3.0:
                    print("🎯 TARGET TERKUNCI! MEMBUKA SERVO SEKARANG!")
                    trigger_servo(master, SERVO_PWM_OPEN)
                    servo_terbuka = True
                    stable_start_time = 0
            else:
                if not servo_terbuka:
                    stable_start_time = 0 # Reset waktu jika melenceng
                    cv2.putText(frame, "ARAHKAN KE TENGAH!", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.putText(frame, "STATUS: TRACKING BOX MERAH", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.putText(frame, "BOX MERAH TIDAK DITEMUKAN", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            stable_start_time = 0

        # Tampilkan Status Servo Besar-besar
        if servo_terbuka:
            cv2.putText(frame, "PAYLOAD DROPPED! (SERVO TERBUKA)", (10, 650), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
            cv2.putText(frame, "(Tekan tombol 'r' di keyboard untuk reset servo)", (10, 690), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        cv2.imshow("Test Deteksi Box Merah & Servo", frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            print("🔄 Resetting Servo ke posisi semula (PWM 1100)")
            trigger_servo(master, SERVO_PWM_CLOSE)
            servo_terbuka = False
            stable_start_time = 0

    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
