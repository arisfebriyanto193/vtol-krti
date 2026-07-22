import time
import sys
from pymavlink import mavutil
import serial.tools.list_ports

# Pastikan output aman di Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def find_pixhawk():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = p.description.lower()
        if "ardupilot" in desc or "pixhawk" in desc or "fmu" in desc or "usb serial device" in desc:
            return p.device
    
    if len(ports) == 1:
        return ports[0].device
    return None

def set_param(master, param_name, param_value):
    print(f"[SETTING] Mengubah {param_name} menjadi {param_value}...")
    master.mav.param_set_send(
        master.target_system, master.target_component,
        param_name.encode('utf-8'),
        float(param_value),
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32
    )
    t0 = time.time()
    while time.time() - t0 < 3:
        msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
        if msg:
            pid = msg.param_id
            if isinstance(pid, bytes):
                pid = pid.decode('utf-8')
            if pid.rstrip('\x00') == param_name:
                print(f"[OK] {param_name} berhasil disetel ke {msg.param_value}")
                return
    print(f"[WARN] Tidak mendapat konfirmasi untuk {param_name} (bisa jadi sudah tersetel).")

def main():
    print("[INFO] Mencari koneksi Pixhawk...")
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("[ERROR] Tidak ada perangkat COM terdeteksi. Pastikan kabel USB tersambung!")
        return
        
    print("Daftar COM Port tersedia:")
    for p in ports:
        print(f"  - {p.device}: {p.description}")

    port = find_pixhawk()
    if not port:
        # Fallback jika fungsi tidak menemukan port spesifik, ambil port terakhir 
        # (seringkali perangkat USB yang baru dicolok muncul di akhir atau COM7)
        port = "COM7"
    
    print(f"\n[INFO] Menghubungkan ke Pixhawk di port {port}...")
    try:
        master = mavutil.mavlink_connection(port, baud=115200)
        master.wait_heartbeat(timeout=5)
        print("[OK] Berhasil terhubung ke Pixhawk!")
    except Exception as e:
        print(f"[ERROR] Gagal terhubung: {e}")
        return

    print("\n[INFO] Menyetel parameter TELEM 1 (SERIAL1) untuk ELRS (CRSF)...")
    set_param(master, "SERIAL1_PROTOCOL", 23)
    set_param(master, "SERIAL1_BAUD", 115)
    
    print("\n[INFO] Menyetel protokol RC...")
    set_param(master, "RC_PROTOCOLS", 512)

    print("\n[SELESAI] PENGATURAN SELESAI!")
    print("[PENTING] Anda HARUS MEREBOOT PIXHAWK SEKARANG (cabut USB & Baterai lalu pasang lagi) agar bisa berfungsi.")



if __name__ == '__main__':
    main()
