"""
Script untuk komunikasi antara Raspberry Pi dan Pixhawk via USB.
Dibutuhkan library pymavlink:
pip3 install pymavlink

Cara menjalankan:
python3 koneksi-pixhawk.py --connect /dev/ttyACM0
"""
from pymavlink import mavutil
import time 
import argparse
import math

# Setup argumen untuk port koneksi (berdasarkan deteksi dmesg/lsusb biasanya /dev/ttyACM0)
parser = argparse.ArgumentParser(description='Komunikasi Raspi - Pixhawk (Pymavlink)')
parser.add_argument('--connect', help="Port koneksi Pixhawk", default='/dev/ttyACM0')
args = parser.parse_args()

print(f"Mencoba terhubung ke Pixhawk pada {args.connect} (Baudrate: 115200)...")
try:
    # Membuat koneksi mavlink
    master = mavutil.mavlink_connection(args.connect, baud=115200)
    print("⏳ Menunggu Heartbeat pertama dari Pixhawk...")
    master.wait_heartbeat()
    print("✅ Berhasil Terhubung ke Pixhawk!\n")
except Exception as e:
    print(f"❌ Gagal terhubung: {e}")
    print("Pastikan kabel USB terpasang dan port benar (cek dengan 'ls /dev/tty*')")
    exit(1)

# Request aliran data (Data Streams) agar Pixhawk rutin mengirim semua data ke Raspi
master.mav.request_data_stream_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1
)
master.mav.request_data_stream_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_DATA_STREAM_EXTRA1, 5, 1 # Untuk ATTITUDE (Roll, Pitch, Yaw)
)
master.mav.request_data_stream_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_DATA_STREAM_RAW_SENSORS, 5, 1 # Untuk RAW_IMU / SCALED_IMU
)

def dapatkan_mode_str(custom_mode):
    """Menerjemahkan custom_mode (angka) menjadi nama mode berdasarkan pemetaan Pixhawk"""
    mode_mapping = master.mode_mapping()
    if mode_mapping:
        for name, mode_id in mode_mapping.items():
            if mode_id == custom_mode:
                return name
    return f"UNKNOWN({custom_mode})"

def baca_data():
    """Membaca pesan-pesan MAVLink yang masuk untuk mendapatkan Telemetri"""
    print("\n" + "="*30)
    
    data_gps = None
    data_compass = None
    data_rc = None
    data_attitude = None
    data_raw_imu = None
    flight_mode = None
    is_armed = False
    
    # Dengarkan pesan MAVLink selama 1.5 detik agar semua paket data tertangkap
    timeout = time.time() + 1.5
    while time.time() < timeout:
        # Menangkap paket spesifik (ditambahkan RC_CHANNELS_RAW untuk Pixhawk lawas/tertentu)
        msg = master.recv_match(type=['GLOBAL_POSITION_INT', 'VFR_HUD', 'RC_CHANNELS', 'RC_CHANNELS_RAW', 'HEARTBEAT', 'ATTITUDE', 'RAW_IMU', 'SCALED_IMU2', 'SCALED_IMU'], blocking=True, timeout=0.1)
        if not msg:
            continue
            
        if msg.get_type() == 'HEARTBEAT':
            flight_mode = dapatkan_mode_str(msg.custom_mode)
            is_armed = (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0
        elif msg.get_type() == 'GLOBAL_POSITION_INT':
            data_gps = msg
        elif msg.get_type() == 'VFR_HUD':
            data_compass = msg.heading
        elif msg.get_type() in ['RC_CHANNELS', 'RC_CHANNELS_RAW']:
            data_rc = msg
        elif msg.get_type() == 'ATTITUDE':
            data_attitude = msg
        elif msg.get_type() in ['RAW_IMU', 'SCALED_IMU2', 'SCALED_IMU']:
            data_raw_imu = msg
            
    # Cetak Hasilnya
    print(f"🧭 Kompas (Heading): {data_compass if data_compass is not None else 'Belum ada data'} derajat")
    
    if data_attitude:
        roll = math.degrees(data_attitude.roll)
        pitch = math.degrees(data_attitude.pitch)
        yaw = math.degrees(data_attitude.yaw)
        yaw = yaw if yaw >= 0 else 360 + yaw
        print(f"📐 Attitude: Roll={roll:.2f}°, Pitch={pitch:.2f}°, Yaw={yaw:.2f}°")
    else:
        print("📐 Attitude: Belum ada data (Memeriksa MAV_DATA_STREAM_EXTRA1...)")
        
    if data_raw_imu:
        print(f"🧲 Magnetometer (Raw/Scaled): X={data_raw_imu.xmag}, Y={data_raw_imu.ymag}, Z={data_raw_imu.zmag}")
    else:
        print("🧲 Magnetometer: Belum ada data (Memeriksa RAW_SENSORS...)")
    
    if data_gps:
        lat = data_gps.lat / 1e7
        lon = data_gps.lon / 1e7
        alt = data_gps.alt / 1000.0 # dalam meter
        print(f"🛰️ GPS: Lat={lat}, Lon={lon}, Alt={alt}m")
    else:
        print("🛰️ GPS: Belum mendapatkan sinyal/data GPS")
        
    print(f"✈️ Flight Mode   : {flight_mode if flight_mode else 'Belum ada data'}")
    
    if is_armed:
        print(f"🚀 Status Drone  : ARMED (Baling-baling aktif!)")
    else:
        print(f"🛑 Status Drone  : DISARMED (Aman)")
    
    print(f"🎮 Data Receiver (RC):") 
    if data_rc:
        for i in range(1, 11): # Menampilkan CH1 - CH10
            val = getattr(data_rc, f'chan{i}_raw', 'N/A')
            label = " [ARMING SWITCH]" if i == 7 else ""
            print(f"   CH{i} (PWM): {val}{label}")
            
        # Logika Auto-Arming/Disarming via Script ketika CH7 diaktifkan
        ch7_pwm = getattr(data_rc, 'chan7_raw', 0)
        if isinstance(ch7_pwm, int) and ch7_pwm > 0:
            if ch7_pwm > 1900 and not is_armed:
                print("\n⚠️ [AUTO] CH7 mendeteksi >1900! Mengirim perintah ARMING otomatis...")
                master.mav.command_long_send(
                    master.target_system, master.target_component,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0
                )
            elif ch7_pwm < 1100 and is_armed:
                print("\n⚠️ [AUTO] CH7 mendeteksi <1100! Mengirim perintah DISARMING otomatis...")
                master.mav.command_long_send(
                    master.target_system, master.target_component,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 0, 0, 0, 0, 0, 0
                )
    else:
        print("   Belum ada data Receiver / Remote tidak nyala")
        
    print("="*30)

def ubah_mode(mode_baru):
    """Mengirim perintah perubahan mode MAVLink ke Pixhawk"""
    mode_mapping = master.mode_mapping()
    if not mode_mapping or mode_baru not in mode_mapping:
        print(f"❌ Mode '{mode_baru}' tidak valid/tidak dikenal oleh Pixhawk.")
        return
        
    mode_id = mode_mapping[mode_baru]
    print(f"\n🔄 Mengirim perintah ganti mode ke: {mode_baru}...")
    
    # Perintah ganti mode standar Pymavlink
    master.set_mode(mode_id)
    
    # Tunggu konfirmasi (ACK) dari Pixhawk apakah perubahan mode diterima atau ditolak
    ack_msg = master.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
    if ack_msg:
        if ack_msg.result == 0:
            print("✅ Perintah ganti mode DITERIMA oleh Pixhawk!")
        else:
            print(f"❌ Pixhawk MENOLAK ganti mode (Error Code: {ack_msg.result}).")
            print("   INFO: Pixhawk biasanya menolak masuk ke mode GUIDED/AUTO/RTL jika GPS belum mendapatkan sinyal 3D Lock!")
    else:
        print("⚠️ Tidak ada respon/konfirmasi dari Pixhawk, namun perintah telah dikirim.")
        
    time.sleep(1) # Beri waktu sejenak agar mode berganti di UI

if __name__ == '__main__':
    try:
        while True:
            # Tampilkan telemetri
            baca_data()
            
            # Tanya input user apakah ingin mengubah mode
            cmd = input("\nKetik mode baru (misal: STABILIZE, GUIDED, RTL, AUTO)\nKetik 'ARM' untuk arming, 'DISARM' untuk disarm\natau cukup tekan [Enter] untuk baca data lagi (Ctrl+C untuk keluar): ").strip().upper()
            
            if cmd == "ARM":
                print("\n🔄 Mengirim perintah ARMING via Mavlink...")
                master.mav.command_long_send(
                    master.target_system,
                    master.target_component,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0, 1, 0, 0, 0, 0, 0, 0
                )
                time.sleep(1)
            elif cmd == "DISARM":
                print("\n🔄 Mengirim perintah DISARMING via Mavlink...")
                master.mav.command_long_send(
                    master.target_system,
                    master.target_component,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0, 0, 0, 0, 0, 0, 0, 0
                )
                time.sleep(1)
            elif cmd != "":
                ubah_mode(cmd)
                
    except KeyboardInterrupt:
        print("\nMenutup program...")
        print("Selesai.")
