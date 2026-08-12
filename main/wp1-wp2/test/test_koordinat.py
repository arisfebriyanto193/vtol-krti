# -*- coding: utf-8 -*-
import sys
import cv2
import numpy as np
import time
from pymavlink import mavutil

# Force UTF-8 output agar karakter unicode muncul di terminal Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# ================= KONFIGURASI =================
CAMERA_INDEX   = 1    # Ganti ke 2 jika kamera yang terlihat bukan yang tepat
LOCK_TOLERANCE = 40   # Toleransi piksel untuk status LOCKED
KP_XY          = 0.0015 # Konstanta Proportional untuk kecepatan (PID)
MAX_SPEED      = 0.3  # Kecepatan maksimal (m/s)
PIXHAWK_PORT   = '/dev/ttyACM0' # Sesuaikan dengan port Pixhawk (misal: COM3 jika di Windows, /dev/ttyACM0 di Raspberry Pi)
PIXHAWK_BAUD   = 115200
# ===============================================

def connect_pixhawk():
    print(f"[INFO] Menghubungkan ke Pixhawk di {PIXHAWK_PORT} ({PIXHAWK_BAUD})...")
    try:
        master = mavutil.mavlink_connection(PIXHAWK_PORT, baud=PIXHAWK_BAUD)
        master.wait_heartbeat(timeout=5)
        if master.target_system == 0:
            print("[WARNING] Tidak ada heartbeat dari Pixhawk! Pastikan port benar.")
            return None
        print("✅ Berhasil Terhubung ke Pixhawk!")
        return master
    except Exception as e:
        print(f"❌ Gagal konek ke Pixhawk: {e}")
        return None

def send_velocity(master, vx, vy, vz):
    if master is None: return
    # Kirim kecepatan NED (North, East, Down). Karena MAV_FRAME_BODY_NED, x=Maju, y=Kanan
    master.mav.set_position_target_local_ned_send(
        0, master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_BODY_NED,
        0b0000111111000111, # Abaikan posisi dan yaw, gunakan velocity
        0, 0, 0, vx, vy, vz, 0, 0, 0, 0, 0
    )

def draw_overlay(frame, cx, cy, marker_id, error_x, error_y, is_locked,
                 center_x_frame, center_y_frame):
    """Menggambar semua visual overlay di atas frame kamera."""

    # --- Warna berdasarkan status ---
    color_box    = (0, 255,   0) if is_locked else (0, 165, 255)  # Hijau / Oranye
    color_line   = (0, 255, 255)                                    # Kuning
    color_cross  = (255,  0,   0)                                   # Biru

    # --- Crosshair titik tengah frame ---
    cv2.line(frame, (center_x_frame - 20, center_y_frame),
                    (center_x_frame + 20, center_y_frame), color_cross, 2)
    cv2.line(frame, (center_x_frame, center_y_frame - 20),
                    (center_x_frame, center_y_frame + 20), color_cross, 2)

    # --- Titik pusat marker + garis ke tengah frame ---
    cv2.circle(frame, (cx, cy), 6, color_box, -1)
    cv2.line(frame, (center_x_frame, center_y_frame), (cx, cy), color_line, 2)

    # --- Lingkaran zona LOCK ---
    cv2.circle(frame, (center_x_frame, center_y_frame), LOCK_TOLERANCE,
               (0, 255, 0) if is_locked else (50, 50, 50), 1)

    # --- Panel info di pojok kiri atas ---
    status_text = "LOCKED" if is_locked else "TRACKING"
    status_color = (0, 255, 0) if is_locked else (0, 165, 255)

    # Background panel semi-transparan
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (400, 105), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

    cv2.putText(frame, f"STATUS   : {status_text}",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)
    cv2.putText(frame, f"Marker ID: {marker_id}",
                (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    cv2.putText(frame, f"Koordinat: X={cx}  Y={cy}",
                (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    cv2.putText(frame, f"Error    : dX={error_x:+d}  dY={error_y:+d}",
                (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

    return frame


def main():
    # 1. Hubungkan Pixhawk
    master = connect_pixhawk()
    if master is None:
        print("[WARNING] Berjalan TANPA pergerakan drone (Hanya Visual) karena Pixhawk tidak terhubung.")
    
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("[ERROR] Gagal membuka kamera.")
        return

    # Inisialisasi ArUco Dictionary (7x7)
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_7X7_1000)
    aruco_params = cv2.aruco.DetectorParameters()
    try:
        aruco_params.minMarkerPerimeterRate = 0.03
    except:
        pass

    has_new_api = hasattr(cv2.aruco, 'ArucoDetector')
    if has_new_api:
        detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    print("[START] Memulai Program Test Koordinat ArUco...")
    print("[INFO]  Tekan 'Q' pada jendela video atau 'Ctrl+C' di terminal untuk keluar.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("[WARNING] Gagal membaca frame dari kamera!")
                break

            h, w, _ = frame.shape
            center_x_frame = w // 2
            center_y_frame = h // 2

            # Deteksi Marker ArUco
            if has_new_api:
                corners, ids, rejected = detector.detectMarkers(frame)
            else:
                corners, ids, rejected = cv2.aruco.detectMarkers(
                    frame, aruco_dict, parameters=aruco_params)

            if ids is not None and len(ids) > 0:
                # Gambar kotak deteksi pada semua marker
                cv2.aruco.drawDetectedMarkers(frame, corners, ids)

                # Ambil marker pertama untuk tracking utama
                marker_id = ids[0][0]
                points    = corners[0][0]

                cx = int(np.mean(points[:, 0]))
                cy = int(np.mean(points[:, 1]))

                error_x   = cx - center_x_frame
                error_y   = cy - center_y_frame
                is_locked = abs(error_x) < LOCK_TOLERANCE and abs(error_y) < LOCK_TOLERANCE

                # --- KONTROL PERGERAKAN DRONE ---
                # Ingat: Kamera menghadap bawah.
                # error_y positif (target di bawah frame) = target di belakang drone = mundur (vx negatif)
                # error_x positif (target di kanan frame) = target di kanan drone = geser kanan (vy positif)
                vx = np.clip(-1.0 * error_y * KP_XY, -MAX_SPEED, MAX_SPEED)
                vy = np.clip(1.0 * error_x * KP_XY, -MAX_SPEED, MAX_SPEED)
                
                # Kirim perintah gerak jika Pixhawk terhubung
                send_velocity(master, vx, vy, 0.0)

                # Gambar overlay visual
                frame = draw_overlay(frame, cx, cy, marker_id, error_x, error_y,
                                     is_locked, center_x_frame, center_y_frame)

                # Print ke terminal
                status = "[LOCKED]  " if is_locked else "[TRACKING]"
                print(f"{status} ID:{marker_id} | dX:{error_x:+d} dY:{error_y:+d} | vX:{vx:+.2f} vY:{vy:+.2f}")

            else:
                # Tidak ada marker — drone diam (Hover)
                send_velocity(master, 0.0, 0.0, 0.0)
                
                # Tampilkan pesan di frame
                cv2.putText(frame, "Mencari marker 7x7... (Hover)",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                # Crosshair tetap ditampilkan
                cv2.line(frame, (center_x_frame - 20, center_y_frame),
                                (center_x_frame + 20, center_y_frame), (255, 0, 0), 2)
                cv2.line(frame, (center_x_frame, center_y_frame - 20),
                                (center_x_frame, center_y_frame + 20), (255, 0, 0), 2)

            # Tampilkan jendela video
            cv2.imshow("Test Koordinat ArUco", frame)

            # Tekan 'q' untuk keluar
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\n[STOP] Program dihentikan.")
    finally:
        send_velocity(master, 0.0, 0.0, 0.0) # Pastikan drone hover saat script mati
        cap.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()