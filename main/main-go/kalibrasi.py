import os
import json
import time
import threading
from flask import Flask, render_template_string, jsonify, request, send_from_directory
from pymavlink import mavutil
from sensor_reader import ESP32Reader

# Path Setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', 'config', 'krti_config.json'))
KOMPONEN_DIR = os.path.join(BASE_DIR, 'komponen')

app = Flask(__name__)

# Global state
master = None
esp_reader = None
config_data = {}

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
    esp_reader = ESP32Reader(port=config_data['esp32_port'], baudrate=config_data.get('esp32_baudrate', 115200))
    esp_reader.start()

# Connect ke Pixhawk
def connect_pixhawk():
    global master
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
            mavutil.mavlink.MAV_DATA_STREAM_ALL, 2, 1
        )
        print("✅ Terhubung ke Pixhawk")
    except Exception as e:
        print(f"❌ Gagal koneksi Pixhawk: {e}")
        master = None

# Jalankan koneksi di awal
threading.Thread(target=connect_pixhawk, daemon=True).start()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KRTI VTOL Dashboard - Kalibrasi</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-accent: #00ff88;
            --secondary-accent: #00b8ff;
            --glass-bg: rgba(11, 15, 25, 0.85);
            --text-main: #ffffff;
        }
        body {
            font-family: 'Outfit', sans-serif;
            margin: 0;
            padding: 20px;
            color: var(--text-main);
            min-height: 100vh;
            background-image: url('{{ bg_image }}');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .overlay {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.6);
            z-index: -1;
        }
        .container {
            background: var(--glass-bg);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 20px;
            padding: 30px;
            max-width: 900px;
            width: 100%;
            box-shadow: 0 10px 40px rgba(0,0,0,0.5);
            margin-top: 20px;
        }
        h1 {
            text-align: center;
            margin-top: 0;
            background: linear-gradient(90deg, var(--primary-accent), var(--secondary-accent));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        select, button {
            font-family: 'Outfit', sans-serif;
            padding: 10px 20px;
            border-radius: 8px;
            border: none;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            transition: 0.3s;
        }
        select {
            background: rgba(255,255,255,0.1);
            color: white;
            border: 1px solid rgba(255,255,255,0.2);
        }
        option { background: #1a2233; color: white; }
        .btn-cal {
            background: linear-gradient(135deg, var(--primary-accent), #00cc6a);
            color: #000;
            font-weight: 700;
            padding: 8px 15px;
            font-size: 0.9rem;
        }
        .btn-cal:hover {
            transform: translateY(-3px);
            box-shadow: 0 5px 15px rgba(0,255,136,0.4);
        }
        .telemetry {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        .card {
            background: rgba(255,255,255,0.05);
            padding: 15px;
            border-radius: 10px;
            border-left: 4px solid var(--secondary-accent);
        }
        .card-title { font-size: 0.9rem; color: #8b9bb4; }
        .card-val { font-size: 1.2rem; font-weight: bold; margin-top: 5px; }
        
        .wp-container {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-top: 20px;
        }
        .wp-card {
            background: rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            padding: 15px;
        }
        .wp-title {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .wp-title h3 {
            margin: 0;
            font-size: 1.1rem;
        }
        .data-text {
            font-size: 0.85rem;
            color: #ccc;
            line-height: 1.4;
        }
    </style>
</head>
<body>
    <div class="overlay"></div>
    <div class="container">
        <h1>🚁 Kalibrasi Lapangan KRTI</h1>
        
        <div class="controls">
            <div>
                <label>Pilih Tim: </label>
                <select id="team-select" onchange="changeTeam()">
                    <option value="Biru" {% if team == 'Biru' %}selected{% endif %}>Tim Biru</option>
                    <option value="Merah" {% if team == 'Merah' %}selected{% endif %}>Tim Merah</option>
                </select>
            </div>
            <div>
                <span id="conn-status" style="color: yellow;">Checking connection...</span>
            </div>
        </div>

        <div class="telemetry">
            <div class="card">
                <div class="card-title">GPS (Pixhawk)</div>
                <div class="card-val" id="val-gps">Menunggu data...</div>
            </div>
            <div class="card">
                <div class="card-title">Alt PX | Alt ESP32</div>
                <div class="card-val" id="val-alt">-- m | -- cm</div>
            </div>
            <div class="card">
                <div class="card-title">Yaw (Heading)</div>
                <div class="card-val" id="val-yaw">-- &deg;</div>
            </div>
        </div>

        <div class="wp-container">
            {% for wp_name in ['wp1', 'wp2', 'wp3', 'wp4', 'wp5'] %}
            <div class="wp-card">
                <div class="wp-title">
                    <h3>{{ wp_name.upper() }}</h3>
                    <button class="btn-cal" onclick="calibrate('{{ wp_name }}')">Kalibrasi</button>
                </div>
                <div class="data-text" id="{{ wp_name }}-data">
                    Lat: {{ wp_data.get(wp_name, {}).get('lat', 0.0) }}<br>
                    Lon: {{ wp_data.get(wp_name, {}).get('lon', 0.0) }}<br>
                    Alt PX: {{ wp_data.get(wp_name, {}).get('alt_pixhawk', 0.0) }} m<br>
                    Alt ESP: {{ wp_data.get(wp_name, {}).get('alt_esp32', 0.0) }} cm<br>
                    Yaw: {{ wp_data.get(wp_name, {}).get('yaw', 0.0) }} &deg;
                </div>
            </div>
            {% endfor %}
        </div>
    </div>

    <script>
        function changeTeam() {
            let t = document.getElementById('team-select').value;
            fetch('/set_team', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({team: t})
            }).then(() => location.reload());
        }

        function calibrate(wp) {
            fetch('/calibrate/' + wp, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if(data.status === 'success') {
                    alert('Kalibrasi ' + wp.toUpperCase() + ' Berhasil!');
                    location.reload();
                } else {
                    alert('Gagal: ' + data.message);
                }
            });
        }

        function updateTelemetry() {
            fetch('/api/telemetry')
            .then(r => r.json())
            .then(data => {
                document.getElementById('conn-status').innerText = (data.pixhawk_connected ? '✅ Pixhawk OK' : '❌ Pixhawk OFF') + ' | ' + (data.esp_connected ? '✅ ESP32 OK' : '❌ ESP32 OFF');
                document.getElementById('conn-status').style.color = (data.pixhawk_connected && data.esp_connected) ? '#00ff88' : 'yellow';
                
                let lat = data.lat ? data.lat.toFixed(7) : '--';
                let lon = data.lon ? data.lon.toFixed(7) : '--';
                document.getElementById('val-gps').innerText = lat + ', ' + lon;
                
                let alt = data.alt_px ? data.alt_px.toFixed(2) : '--';
                let esp_alt = data.alt_esp ? data.alt_esp.toFixed(1) : '--';
                document.getElementById('val-alt').innerText = alt + ' m | ' + esp_alt + ' cm';
                
                let yaw = data.yaw !== null ? data.yaw.toFixed(1) : '--';
                document.getElementById('val-yaw').innerHTML = yaw + ' &deg;';
            });
        }

        setInterval(updateTelemetry, 500);
    </script>
</body>
</html>
"""

@app.route('/komponen/<path:filename>')
def serve_komponen(filename):
    return send_from_directory(KOMPONEN_DIR, filename)

@app.route('/')
def index():
    load_config()
    team = config_data.get('team', 'Biru')
    # Background dinamis sesuai tim
    bg_image = '/komponen/tim-biru/image.png' if team == 'Biru' else '/komponen/tim-merah/image.png'
    wp_key = f'waypoints_{team}'
    wp_data = config_data.get(wp_key, {})
    return render_template_string(HTML_TEMPLATE, team=team, bg_image=bg_image, wp_data=wp_data)

@app.route('/set_team', methods=['POST'])
def set_team():
    data = request.json
    config_data['team'] = data.get('team', 'Biru')
    save_config()
    return jsonify({"status": "success"})

@app.route('/api/telemetry')
def api_telemetry():
    global master, esp_reader
    lat, lon, alt_px, yaw = 0.0, 0.0, 0.0, 0.0
    px_conn = False
    
    if master is not None:
        px_conn = True
        msg = master.recv_match(type=['GLOBAL_POSITION_INT'], blocking=False)
        if msg:
            lat = msg.lat / 1e7
            lon = msg.lon / 1e7
            alt_px = msg.relative_alt / 1000.0
            yaw = msg.hdg / 100.0 if msg.hdg != 65535 else 0.0

    alt_esp = esp_reader.get_bottom_distance() if esp_reader else 0.0
    esp_conn = esp_reader.running if esp_reader else False

    return jsonify({
        "pixhawk_connected": px_conn,
        "esp_connected": esp_conn,
        "lat": lat,
        "lon": lon,
        "alt_px": alt_px,
        "alt_esp": alt_esp,
        "yaw": yaw
    })

@app.route('/calibrate/<wp>', methods=['POST'])
def calibrate(wp):
    global master, esp_reader
    valid_wps = ['wp1', 'wp2', 'wp3', 'wp4', 'wp5']
    if wp not in valid_wps:
        return jsonify({"status": "error", "message": "WP tidak valid"}), 400

    if not master:
        return jsonify({"status": "error", "message": "Pixhawk tidak terhubung"}), 400

    # Ambil latest GPS & Heading
    msg = master.recv_match(type=['GLOBAL_POSITION_INT'], blocking=True, timeout=2.0)
    if not msg:
        return jsonify({"status": "error", "message": "Gagal mendapatkan koordinat GPS (Tidak ada fix)"}), 400

    lat = msg.lat / 1e7
    lon = msg.lon / 1e7
    alt_px = msg.relative_alt / 1000.0
    yaw = msg.hdg / 100.0 if msg.hdg != 65535 else 0.0
    
    alt_esp = esp_reader.get_bottom_distance() if esp_reader else 0.0

    team = config_data.get('team', 'Biru')
    wp_key = f'waypoints_{team}'

    if wp_key not in config_data:
        config_data[wp_key] = {}
    
    config_data[wp_key][wp] = {
        "lat": lat,
        "lon": lon,
        "alt_pixhawk": round(alt_px, 2),
        "alt_esp32": round(alt_esp, 2),
        "yaw": round(yaw, 2)
    }
    save_config()
    return jsonify({"status": "success", "data": config_data[wp_key][wp]})

if __name__ == '__main__':
    print("🚀 Memulai Web Server Kalibrasi di port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)