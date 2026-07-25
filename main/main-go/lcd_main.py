import os
import json
import time
import threading
import subprocess
import math

import board
import digitalio
import adafruit_rgb_display.ili9341 as ili9341
from PIL import Image, ImageDraw, ImageFont

from pymavlink import mavutil
from sensor_reader import ESP32Reader

# Path Setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', 'config', 'krti_config.json'))

# Global state
config_data = {}
master = None
esp_reader = None

drone_lat = 0.0
drone_lon = 0.0
drone_alt_px = 0.0
drone_yaw = 0.0

def load_config():
    global config_data
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            config_data = json.load(f)
    else:
        print(f"[WARNING] Config tidak ditemukan di {CONFIG_PATH}")

def save_config():
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config_data, f, indent=4)

load_config()

# Coba connect ke ESP32
if config_data.get('esp32_port'):
    try:
        esp_reader = ESP32Reader(port=config_data['esp32_port'], baudrate=config_data.get('esp32_baudrate', 115200))
        esp_reader.start()
    except Exception as e:
        print(f"Gagal konek ESP32: {e}")

def pixhawk_loop():
    global master, drone_lat, drone_lon, drone_alt_px, drone_yaw
    port = config_data.get('pixhawk_port')
    baud = config_data.get('pixhawk_baudrate', 115200)
    if not port:
        return
    try:
        print(f"Menghubungkan ke Pixhawk di {port}...")
        master = mavutil.mavlink_connection(port, baud=baud)
        master.wait_heartbeat(timeout=3)
        master.mav.request_data_stream_send(
            master.target_system, master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1
        )
        print("✅ Terhubung ke Pixhawk")
    except Exception as e:
        print(f"❌ Gagal koneksi Pixhawk: {e}")
        master = None
        return

    while True:
        try:
            msg = master.recv_match(blocking=True, timeout=1.0)
            if msg:
                msg_type = msg.get_type()
                if msg_type == 'GLOBAL_POSITION_INT':
                    drone_lat = msg.lat / 1e7
                    drone_lon = msg.lon / 1e7
                    drone_alt_px = msg.relative_alt / 1000.0
                elif msg_type == 'ATTITUDE':
                    yaw_deg = math.degrees(msg.yaw)
                    if yaw_deg < 0:
                        yaw_deg += 360
                    drone_yaw = yaw_deg
        except Exception:
            time.sleep(0.1)

# Jalankan koneksi telemetry di background
threading.Thread(target=pixhawk_loop, daemon=True).start()

# Inisialisasi LCD
cs_pin = digitalio.DigitalInOut(board.CE0)
dc_pin = digitalio.DigitalInOut(board.D25)
reset_pin = digitalio.DigitalInOut(board.D24)
spi = board.SPI()

display = ili9341.ILI9341(
    spi,
    rotation=90, 
    width=320,  
    height=240,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=24000000,
)

# Inisialisasi Tombol (Pull Up)
btn_prev = digitalio.DigitalInOut(board.D17)
btn_prev.direction = digitalio.Direction.INPUT
btn_prev.pull = digitalio.Pull.UP

btn_next = digitalio.DigitalInOut(board.D27)
btn_next.direction = digitalio.Direction.INPUT
btn_next.pull = digitalio.Pull.UP

btn_ok = digitalio.DigitalInOut(board.D22)
btn_ok.direction = digitalio.Direction.INPUT
btn_ok.pull = digitalio.Pull.UP

# Konstanta UI
WIDTH = 320
HEIGHT = 240
image = Image.new("RGB", (WIDTH, HEIGHT))
draw = ImageDraw.Draw(image)

try:    
    font_main = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
except IOError:
    font_main = ImageFont.load_default()
    font_small = ImageFont.load_default()

# State Machine UI
# 0 = Main Menu
# 1 = Kalibrasi Menu
# 2 = Play Menu
# 3 = Play per WP Menu
# 4 = Misi Sedang Berjalan
state = 0

main_menu_items = ["Menu Kalibrasi", "Menu Play", "Ganti Tim", "Info & WiFi"]
main_menu_idx = 0

team_menu_items = ["Biru", "Merah", "Kembali"]
team_menu_idx = 0

kalibrasi_wps = ["wp1", "wp2", "wp3", "wp4", "wp5", "Kembali"]
kalibrasi_idx = 0
kalibrasi_msg = ""
kalibrasi_msg_time = 0

play_menu_items = ["Play All", "Play per WP", "Kembali"]
play_menu_idx = 0

play_wp_items = ["wp1-wp2", "wp2-wp3", "wp3-wp4", "wp4-wp5", "Kembali"]
play_wp_idx = 0

info_menu_items = ["Pindai WiFi Baru", "Kembali"]
info_menu_idx = 0

scanned_wifis = []
wifi_scan_idx = 0
is_scanning = False
wifi_msg = ""
wifi_msg_time = 0

running_mission = None

def get_text_size(text, font):
    left, top, right, bottom = font.getbbox(text)
    return (right - left, bottom - top)

def render_menu(title, items, selected_idx):
    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=(0, 0, 0))
    # Title (Warna Cyan terbalik: BGR = 255, 255, 0)
    title_w, _ = get_text_size(title, font_main)
    draw.text(((WIDTH - title_w) // 2, 10), title, font=font_main, fill=(0, 255, 255))
    
    start_y = 50
    for i, item in enumerate(items):
        color = (0, 0, 255) if i == selected_idx else (255, 255, 255) # Merah jika terpilih
        prefix = "> " if i == selected_idx else "  "
        draw.text((20, start_y + (i * 25)), prefix + item, font=font_main, fill=color)
    
    display.image(image, rotation=0)

def render_kalibrasi():
    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=(0, 0, 0))
    
    wp_name = kalibrasi_wps[kalibrasi_idx]
    team = config_data.get('team', 'Biru')
    title = f"Kalib ({team}): {wp_name.upper()}"
    title_w, _ = get_text_size(title, font_main)
    draw.text(((WIDTH - title_w) // 2, 5), title, font=font_main, fill=(0, 255, 255))
    
    alt_esp = esp_reader.get_bottom_distance() if esp_reader else 0.0
    
    draw.text((10, 40), f"Lat: {drone_lat:.7f}", font=font_small, fill=(255, 255, 255))
    draw.text((10, 60), f"Lon: {drone_lon:.7f}", font=font_small, fill=(255, 255, 255))
    draw.text((10, 80), f"Alt PX: {drone_alt_px:.2f} m", font=font_small, fill=(255, 255, 255))
    draw.text((10, 100), f"Alt ESP: {alt_esp:.1f} cm", font=font_small, fill=(255, 255, 255))
    draw.text((10, 120), f"Yaw: {drone_yaw:.1f} deg", font=font_small, fill=(255, 255, 255))
    
    # Target Alt selalu 1 meter
    draw.text((10, 150), "Target Alt: 1.0 m", font=font_main, fill=(0, 255, 0))
    
    draw.text((10, 200), "[Prev] [Next] Ganti WP | [OK] Save", font=font_small, fill=(180, 180, 180))
    
    if time.time() - kalibrasi_msg_time < 3:
        draw.text((10, 175), kalibrasi_msg, font=font_small, fill=(0, 255, 255))
        
    display.image(image, rotation=0)

def render_running():
    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=(0, 0, 0))
    title = "Misi Sedang Berjalan"
    title_w, _ = get_text_size(title, font_main)
    draw.text(((WIDTH - title_w) // 2, 50), title, font=font_main, fill=(0, 255, 255))
    
    draw.text((20, 100), f"Script: {running_mission}", font=font_small, fill=(255, 255, 255))
    draw.text((20, 180), "Misi ini berjalan di background.", font=font_small, fill=(200, 200, 200))
    display.image(image, rotation=0)

def handle_kalibrasi_save():
    global kalibrasi_msg, kalibrasi_msg_time, state
    wp = kalibrasi_wps[kalibrasi_idx]
    
    if wp == "Kembali":
        state = 0
        return
    
    if not master or (drone_lat == 0.0 and drone_lon == 0.0):
        kalibrasi_msg = "Error: Menunggu data Pixhawk..."
        kalibrasi_msg_time = time.time()
        return

    alt_esp = esp_reader.get_bottom_distance() if esp_reader else 0.0
    team = config_data.get('team', 'Biru')
    wp_key = f'waypoints_{team}'

    if wp_key not in config_data:
        config_data[wp_key] = {}
    
    config_data[wp_key][wp] = {
        "lat": drone_lat,
        "lon": drone_lon,
        "alt_pixhawk": round(drone_alt_px, 2),
        "alt_esp32": round(alt_esp, 2),
        "yaw": round(drone_yaw, 2),
        "target_alt": 1.0 # Fix 1 meter
    }
    save_config()
    kalibrasi_msg = f"{wp.upper()} Disimpan!"
    kalibrasi_msg_time = time.time()

def get_ip_address():
    try:
        ip = subprocess.check_output(['hostname', '-I'], text=True).strip()
        return ip if ip else "Tidak ada IP"
    except Exception as e:
        print(f"Error get_ip: {e}")
        return "Error"

def get_current_wifi():
    try:
        wifi = subprocess.check_output(['iwgetid', '-r'], text=True).strip()
        return wifi if wifi else "Tidak Konek"
    except Exception as e:
        print(f"Error get_wifi: {e}")
        return "Error"
        
def scan_wifi():
    try:
        raw = subprocess.check_output(['sudo', 'nmcli', '-t', '-f', 'ssid', 'dev', 'wifi'], text=True)
        ssids = list(set([s.strip() for s in raw.split('\n') if s.strip()]))
        ssids.sort()
        if not ssids: return ["Tidak ada WiFi", "Kembali"]
        ssids.append("Kembali")
        return ssids
    except Exception as e:
        print(f"Error scan_wifi: {e}")
        return ["Gagal Scan", "Kembali"]

def render_info_wifi():
    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=(0, 0, 0))
    title = "Info Sistem & WiFi"
    title_w, _ = get_text_size(title, font_main)
    draw.text(((WIDTH - title_w) // 2, 5), title, font=font_main, fill=(0, 255, 255))
    
    ip_addr = get_ip_address()
    curr_wifi = get_current_wifi()
    
    draw.text((20, 45), f"IP: {ip_addr}", font=font_small, fill=(255, 255, 255))
    draw.text((20, 70), f"WiFi: {curr_wifi}", font=font_small, fill=(255, 255, 255))
    
    start_y = 120
    for i, item in enumerate(info_menu_items):
        color = (0, 0, 255) if i == info_menu_idx else (255, 255, 255)
        prefix = "> " if i == info_menu_idx else "  "
        draw.text((20, start_y + (i * 30)), prefix + item, font=font_main, fill=color)
        
    display.image(image, rotation=0)

def render_wifi_scanner():
    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=(0, 0, 0))
    title = "Pilih WiFi Baru"
    title_w, _ = get_text_size(title, font_main)
    draw.text(((WIDTH - title_w) // 2, 5), title, font=font_main, fill=(0, 255, 255))
    
    if is_scanning:
        draw.text((20, 100), "Memindai WiFi di sekitar...", font=font_small, fill=(255, 255, 255))
    else:
        visible_items = 6
        start_idx = max(0, wifi_scan_idx - visible_items // 2)
        end_idx = min(len(scanned_wifis), start_idx + visible_items)
        if end_idx - start_idx < visible_items:
            start_idx = max(0, end_idx - visible_items)
            
        start_y = 40
        for i in range(start_idx, end_idx):
            item = scanned_wifis[i]
            if len(item) > 20: item = item[:17] + "..."
            color = (0, 0, 255) if i == wifi_scan_idx else (255, 255, 255)
            prefix = "> " if i == wifi_scan_idx else "  "
            draw.text((10, start_y + ((i - start_idx) * 25)), prefix + item, font=font_main, fill=color)
            
        if time.time() - wifi_msg_time < 3:
            draw.text((10, 210), wifi_msg, font=font_small, fill=(0, 255, 255))
            
    display.image(image, rotation=0)

def render_team():
    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=(0, 0, 0))
    title = "Ganti Tim Aktif"
    title_w, _ = get_text_size(title, font_main)
    draw.text(((WIDTH - title_w) // 2, 10), title, font=font_main, fill=(0, 255, 255))
    
    current_team = config_data.get('team', 'Biru')
    draw.text((20, 50), f"Tim Saat Ini: {current_team}", font=font_small, fill=(0, 255, 0))
    
    start_y = 100
    for i, item in enumerate(team_menu_items):
        color = (0, 0, 255) if i == team_menu_idx else (255, 255, 255)
        prefix = "> " if i == team_menu_idx else "  "
        draw.text((20, start_y + (i * 30)), prefix + item, font=font_main, fill=color)
        
    display.image(image, rotation=0)

def run_mission(script_name):
    global state, running_mission
    running_mission = script_name
    state = 4
    script_path = os.path.join(BASE_DIR, script_name)
    print(f"Menjalankan misi: {script_path}")
    # Run independent process
    subprocess.Popen(["python", script_path])
    time.sleep(3) # Tampilkan tulisan berjalan sebentar
    # Kembali ke menu utama
    state = 0
    
def loop_ui():
    global state, main_menu_idx, kalibrasi_idx, play_menu_idx, play_wp_idx
    global info_menu_idx, wifi_scan_idx, is_scanning, scanned_wifis, wifi_msg, wifi_msg_time
    global team_menu_idx
    
    prev_pressed = False
    next_pressed = False
    ok_pressed = False

    while True:
        # Read buttons (Active LOW)
        btn_p = not btn_prev.value
        btn_n = not btn_next.value
        btn_o = not btn_ok.value

        if btn_p and not prev_pressed:
            if state == 0: main_menu_idx = (main_menu_idx - 1) % len(main_menu_items)
            elif state == 1: kalibrasi_idx = (kalibrasi_idx - 1) % len(kalibrasi_wps)
            elif state == 2: play_menu_idx = (play_menu_idx - 1) % len(play_menu_items)
            elif state == 3: play_wp_idx = (play_wp_idx - 1) % len(play_wp_items)
            elif state == 5: info_menu_idx = (info_menu_idx - 1) % len(info_menu_items)
            elif state == 6:
                if not is_scanning and scanned_wifis:
                    wifi_scan_idx = (wifi_scan_idx - 1) % len(scanned_wifis)
            elif state == 7: team_menu_idx = (team_menu_idx - 1) % len(team_menu_items)
            
        if btn_n and not next_pressed:
            if state == 0: main_menu_idx = (main_menu_idx + 1) % len(main_menu_items)
            elif state == 1: kalibrasi_idx = (kalibrasi_idx + 1) % len(kalibrasi_wps)
            elif state == 2: play_menu_idx = (play_menu_idx + 1) % len(play_menu_items)
            elif state == 3: play_wp_idx = (play_wp_idx + 1) % len(play_wp_items)
            elif state == 5: info_menu_idx = (info_menu_idx + 1) % len(info_menu_items)
            elif state == 6:
                if not is_scanning and scanned_wifis:
                    wifi_scan_idx = (wifi_scan_idx + 1) % len(scanned_wifis)
            elif state == 7: team_menu_idx = (team_menu_idx + 1) % len(team_menu_items)
            
        if btn_o and not ok_pressed:
            if state == 0:
                if main_menu_idx == 0: state = 1
                elif main_menu_idx == 1: state = 2
                elif main_menu_idx == 2: state = 7
                elif main_menu_idx == 3: state = 5
            elif state == 1:
                handle_kalibrasi_save()
            elif state == 2:
                if play_menu_idx == 0:
                    run_mission("main.py")
                elif play_menu_idx == 1:
                    state = 3
                elif play_menu_idx == 2:
                    state = 0
            elif state == 3:
                if play_wp_idx == 4: # Kembali
                    state = 2
                else:
                    script = play_wp_items[play_wp_idx] + ".py"
                    run_mission(script)
            elif state == 5:
                if info_menu_idx == 0:
                    state = 6
                    is_scanning = True
                elif info_menu_idx == 1:
                    state = 0
            elif state == 6:
                if not is_scanning and scanned_wifis:
                    selected = scanned_wifis[wifi_scan_idx]
                    if selected == "Kembali" or selected == "Tidak ada WiFi" or selected == "Gagal Scan":
                        state = 5
                    else:
                        wifi_msg = f"Connect {selected[:5]}..."
                        wifi_msg_time = time.time()
                        render_wifi_scanner() # force render to show message
                        try:
                            subprocess.run(['sudo', 'nmcli', 'dev', 'wifi', 'connect', selected], timeout=15)
                            wifi_msg = "Selesai!"
                        except Exception:
                            wifi_msg = "Gagal koneksi!"
                        wifi_msg_time = time.time()
            elif state == 7:
                if team_menu_idx == 0:
                    config_data['team'] = 'Biru'
                    save_config()
                    state = 0
                elif team_menu_idx == 1:
                    config_data['team'] = 'Merah'
                    save_config()
                    state = 0
                elif team_menu_idx == 2:
                    state = 0

        prev_pressed = btn_p
        next_pressed = btn_n
        ok_pressed = btn_o

        if state == 6 and is_scanning:
            render_wifi_scanner()
            scanned_wifis = scan_wifi()
            wifi_scan_idx = 0
            is_scanning = False

        # Render
        if state == 0: render_menu("Main Menu", main_menu_items, main_menu_idx)
        elif state == 1: render_kalibrasi()
        elif state == 2: render_menu("Menu Play", play_menu_items, play_menu_idx)
        elif state == 3: render_menu("Pilih WP", play_wp_items, play_wp_idx)
        elif state == 4: render_running()
        elif state == 5: render_info_wifi()
        elif state == 6 and not is_scanning: render_wifi_scanner()
        elif state == 7: render_team()

        time.sleep(0.1)

if __name__ == '__main__':
    print("🚀 Memulai LCD Main Interface...")
    try:
        loop_ui()
    except KeyboardInterrupt:
        print("Selesai.")
        draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=(0, 0, 0))
        display.image(image, rotation=0)
