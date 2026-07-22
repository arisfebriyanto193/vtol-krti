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

def get_param(master, param_name):
    master.mav.param_request_read_send(
        master.target_system, master.target_component,
        param_name.encode('utf-8'),
        -1
    )
    t0 = time.time()
    while time.time() - t0 < 2:
        msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
        if msg:
            pid = msg.param_id
            if isinstance(pid, bytes):
                pid = pid.decode('utf-8')
            if pid.rstrip('\x00') == param_name:
                return msg.param_value
    return None

def main():
    port = find_pixhawk()
    print(f"[INFO] Menghubungkan ke Pixhawk di port {port}...")
    try:
        master = mavutil.mavlink_connection(port, baud=115200)
        master.wait_heartbeat(timeout=5)
        print("[OK] Terhubung!")
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    params_to_check = [
        "SERIAL1_PROTOCOL", "SERIAL1_BAUD", "SERIAL1_OPTIONS",
        "SERIAL2_PROTOCOL", "SERIAL2_BAUD", "SERIAL2_OPTIONS",
        "BRD_SER1_RTSCTS", "BRD_SER2_RTSCTS",
        "RC_PROTOCOLS", "RSSI_TYPE", "BRD_ALT_CONFIG"
    ]
    
    print("\n--- NILAI PARAMETER SAAT INI ---")
    for p in params_to_check:
        val = get_param(master, p)
        if val is not None:
            print(f"{p} = {val}")
        else:
            print(f"{p} = [TIDAK DITEMUKAN DI FIRMWARE INI]")

if __name__ == '__main__':
    main()
