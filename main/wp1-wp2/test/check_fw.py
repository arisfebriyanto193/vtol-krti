import time
import sys
from pymavlink import mavutil
import serial.tools.list_ports

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
    return "COM7"

def main():
    port = find_pixhawk()
    print(f"[INFO] Menghubungkan ke Pixhawk di port {port}...")
    try:
        master = mavutil.mavlink_connection(port, baud=115200)
        master.wait_heartbeat(timeout=5)
        
        # Minta versi firmware
        master.mav.autopilot_version_request_send(master.target_system, master.target_component)
        msg = master.recv_match(type='AUTOPILOT_VERSION', blocking=True, timeout=3)
        if msg:
            major = msg.flight_sw_version >> 24 & 0xFF
            minor = msg.flight_sw_version >> 16 & 0xFF
            patch = msg.flight_sw_version >> 8 & 0xFF
            print(f"Versi Firmware Pixhawk: {major}.{minor}.{patch}")
        else:
            print("Gagal membaca versi firmware.")
    except Exception as e:
        print(f"[ERROR] {e}")
        return

if __name__ == '__main__':
    main()
