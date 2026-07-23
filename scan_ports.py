import serial.tools.list_ports
import glob
import subprocess

def scan_serial_ports():
    ports = serial.tools.list_ports.comports()
    pixhawk_port = None
    esp32_port = None
    
    print("Mencari perangkat Serial...")
    for port in ports:
        desc = str(port.description).lower()
        hwid = str(port.hwid).lower()
        manufacturer = str(port.manufacturer or "").lower()
        
        print(f" - Ditemukan: {port.device} | Desk: {port.description} | HWID: {port.hwid}")
        
        # Deteksi Pixhawk
        if "ardupilot" in desc or "px4" in desc or "pixhawk" in desc or "ardupilot" in manufacturer or "px4" in manufacturer:
            pixhawk_port = port.device
        elif "usb_device" in hwid and ("26ac:0011" in hwid or "2dae:1016" in hwid or "1209:5741" in hwid):
             # Beberapa VID:PID spesifik Pixhawk
            pixhawk_port = port.device
            
        # Deteksi ESP32
        elif "cp210" in desc or "ch340" in desc or "ftdi" in desc or "espressif" in desc or "ch34" in hwid or "cp21" in hwid or "uart" in desc:
            esp32_port = port.device
            
    return pixhawk_port, esp32_port

def scan_cameras():
    print("\nMencari Kamera...")
    cameras = []
    video_devices = glob.glob("/dev/video*")
    
    if not video_devices:
        return cameras

    try:
        # Menjalankan v4l2-ctl untuk detail jika terinstall
        output = subprocess.check_output(['v4l2-ctl', '--list-devices'], stderr=subprocess.STDOUT).decode()
        print("Detail Kamera (v4l2-ctl):")
        print(output.strip())
        
        for dev in video_devices:
            if dev in output:
                cameras.append(dev)
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Jika tidak ada v4l2-ctl, cetak biasa
        for dev in video_devices:
            cameras.append(dev)
            print(f" - Ditemukan: {dev}")
            
    return cameras

def main():
    print("="*50)
    print(" SCANNER PORT (PIXHAWK, ESP32, KAMERA)")
    print("="*50)
    
    pixhawk, esp32 = scan_serial_ports()
    cameras = scan_cameras()
    
    print("\n" + "="*50)
    print(" HASIL KESIMPULAN SCAN")
    print("="*50)
    
    if pixhawk:
        print(f"[+] PIXHAWK terdeteksi di port : {pixhawk}")
    else:
        print("[-] PIXHAWK TIDAK ditemukan.")
        
    if esp32:
        print(f"[+] ESP32   terdeteksi di port : {esp32}")
    else:
        print("[-] ESP32   TIDAK ditemukan.")
        
    if cameras:
        main_cams = [c for c in cameras if c.replace('/dev/video', '').isdigit()]
        main_cams.sort(key=lambda x: int(x.replace('/dev/video', '')))
        
        if main_cams:
            idx = main_cams[0].replace('/dev/video', '')
            print(f"[+] KAMERA  terdeteksi di port : {', '.join(main_cams)}")
            print(f"    -> Untuk kode Python (OpenCV), gunakan index: cv2.VideoCapture({idx})")
        else:
            print(f"[+] KAMERA  terdeteksi di port : {', '.join(cameras)}")
    else:
        print("[-] KAMERA  TIDAK ditemukan.")
        
    print("="*50)

if __name__ == "__main__":
    main()
