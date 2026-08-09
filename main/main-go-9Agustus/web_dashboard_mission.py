import os
import json
import threading
import logging
from flask import Flask, render_template_string, jsonify, send_from_directory

app = Flask(__name__)
# Nonaktifkan log Flask agar tidak spam terminal
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

shared_data = {
    "mode": "UNKNOWN",
    "state_str": "INIT",
    "lat": 0.0,
    "lon": 0.0,
    "alt": 0.0,
    "yaw": 0.0,
    "roll": 0.0,
    "pitch": 0.0,
    "battery": -1,
    "team": "Biru"
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KOMPONEN_DIR = os.path.join(BASE_DIR, 'komponen')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KRTI VTOL - Mission HUD</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;500;700;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-accent: #00ff88;
            --secondary-accent: #00b8ff;
            --alert-accent: #ff3366;
            --glass-bg: rgba(10, 15, 30, 0.7);
            --text-main: #ffffff;
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'Outfit', sans-serif;
            margin: 0;
            padding: 0;
            color: var(--text-main);
            height: 100vh;
            width: 100vw;
            background-image: url('{{ bg_image }}');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            overflow: hidden;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .overlay {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.4);
            z-index: 0;
        }
        .hud-container {
            position: relative;
            z-index: 10;
            width: 95%;
            height: 90%;
            display: grid;
            grid-template-columns: 250px 1fr 250px;
            grid-template-rows: 1fr;
            gap: 20px;
        }
        
        /* Panel Kiri & Kanan */
        .side-panel {
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 15px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }

        .hud-title {
            text-align: center;
            font-size: 1.2rem;
            font-weight: 700;
            color: var(--secondary-accent);
            text-transform: uppercase;
            letter-spacing: 2px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 10px;
            margin-bottom: 10px;
        }

        .data-box {
            background: rgba(0,0,0,0.4);
            padding: 15px;
            border-radius: 10px;
            border-left: 4px solid var(--primary-accent);
        }
        .data-label {
            font-size: 0.8rem;
            color: #8b9bb4;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 5px;
        }
        .data-value {
            font-size: 1.4rem;
            font-weight: 700;
            font-family: monospace;
        }

        /* Status & Mode Text yang menonjol */
        .status-box {
            background: linear-gradient(135deg, rgba(0,184,255,0.2), rgba(0,255,136,0.2));
            border: 1px solid var(--primary-accent);
            text-align: center;
        }
        .status-text {
            font-size: 1.1rem;
            font-weight: 900;
            color: var(--primary-accent);
            text-shadow: 0 0 10px var(--primary-accent);
            margin-top: 5px;
        }

        /* Center Panel - Artificial Horizon / Visuals */
        .center-panel {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            position: relative;
        }

        /* Horizon Buatan CSS */
        .horizon-circle {
            width: 350px;
            height: 350px;
            border-radius: 50%;
            border: 4px solid rgba(255,255,255,0.3);
            overflow: hidden;
            position: relative;
            box-shadow: 0 0 40px rgba(0,0,0,0.8) inset, 0 0 20px rgba(0,255,136,0.3);
            background-color: #3f7bb5; /* Warna langit standar */
        }
        
        .ground {
            position: absolute;
            width: 200%;
            height: 200%;
            left: -50%;
            top: 50%;
            background-color: #7b593f; /* Warna tanah */
            border-top: 4px solid #fff;
            transform-origin: center top;
            transition: transform 0.1s linear;
        }

        .crosshair {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 140px;
            height: 20px;
            z-index: 2;
        }
        .crosshair::before, .crosshair::after {
            content: '';
            position: absolute;
            background: var(--primary-accent);
            height: 4px;
            top: 8px;
            box-shadow: 0 0 5px var(--primary-accent);
        }
        .crosshair::before { left: 0; width: 40px; }
        .crosshair::after { right: 0; width: 40px; }
        .crosshair-center {
            position: absolute;
            width: 10px;
            height: 10px;
            background: var(--primary-accent);
            border-radius: 50%;
            top: 5px;
            left: 65px;
            box-shadow: 0 0 5px var(--primary-accent);
        }

        .pitch-scale {
            position: absolute;
            top: 0; left: 50%;
            width: 100px;
            height: 200%;
            transform: translateX(-50%);
            transition: transform 0.1s linear;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 1;
        }
        .pitch-line {
            width: 40px;
            height: 2px;
            background: rgba(255,255,255,0.7);
            margin: 20px 0;
        }
        .pitch-line.long { width: 80px; }

        /* Kompas & Yaw */
        .compass-container {
            width: 100%;
            height: 60px;
            background: rgba(0,0,0,0.5);
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.2);
            margin-top: 20px;
            position: relative;
            overflow: hidden;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .compass-scale {
            display: flex;
            transition: transform 0.1s linear;
            white-space: nowrap;
            position: absolute;
        }
        .compass-tick {
            width: 40px;
            text-align: center;
            font-size: 0.8rem;
            color: #aaa;
            display: inline-block;
            position: relative;
        }
        .compass-tick::before {
            content: '';
            position: absolute;
            top: -10px; left: 50%;
            transform: translateX(-50%);
            width: 2px; height: 8px;
            background: #fff;
        }
        .compass-tick.major::before { height: 12px; background: var(--primary-accent); }
        .compass-tick.major { font-weight: bold; color: #fff; }
        
        .compass-pointer {
            position: absolute;
            top: 0; left: 50%;
            transform: translateX(-50%);
            width: 0; height: 0;
            border-left: 10px solid transparent;
            border-right: 10px solid transparent;
            border-top: 15px solid var(--primary-accent);
            z-index: 2;
            filter: drop-shadow(0 0 5px var(--primary-accent));
        }

        /* Battery Animasi */
        .battery-box {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-top: auto;
            background: rgba(0,0,0,0.4);
            padding: 15px;
            border-radius: 10px;
        }
        .battery-body {
            width: 60px;
            height: 25px;
            border: 2px solid #fff;
            border-radius: 4px;
            padding: 2px;
            position: relative;
        }
        .battery-body::after {
            content: '';
            position: absolute;
            right: -6px; top: 5px;
            width: 4px; height: 10px;
            background: #fff;
            border-radius: 0 2px 2px 0;
        }
        .battery-fill {
            height: 100%;
            width: 0%;
            background: var(--primary-accent);
            border-radius: 2px;
            transition: width 0.5s ease, background 0.5s ease;
        }
        .battery-text {
            font-size: 1.2rem;
            font-weight: 700;
        }

        /* Blinking Alert Class */
        .alert-blink {
            animation: blink 1s infinite alternate;
            color: var(--alert-accent);
        }
        @keyframes blink {
            0% { text-shadow: 0 0 5px var(--alert-accent); }
            100% { text-shadow: 0 0 20px var(--alert-accent), 0 0 30px var(--alert-accent); }
        }

    </style>
</head>
<body>
    <div class="overlay"></div>
    <div class="hud-container">
        <!-- Panel Kiri: Navigasi & Posisi -->
        <div class="side-panel">
            <div class="hud-title">Navigation</div>
            
            <div class="data-box">
                <div class="data-label">Latitude</div>
                <div class="data-value" id="val-lat">0.0000000</div>
            </div>
            <div class="data-box">
                <div class="data-label">Longitude</div>
                <div class="data-value" id="val-lon">0.0000000</div>
            </div>
            <div class="data-box">
                <div class="data-label">Altitude (Rel)</div>
                <div class="data-value" id="val-alt">0.0 m</div>
            </div>
            
            <div class="battery-box">
                <div class="battery-body">
                    <div class="battery-fill" id="batt-fill"></div>
                </div>
                <div class="battery-text" id="batt-txt">--%</div>
            </div>
        </div>

        <!-- Panel Tengah: Instrumen Visual -->
        <div class="center-panel">
            <div class="horizon-circle">
                <div class="ground" id="horizon-ground"></div>
                <div class="pitch-scale" id="pitch-scale">
                    <!-- Garis scale pitch digenerate via JS biar gampang -->
                </div>
                <div class="crosshair">
                    <div class="crosshair-center"></div>
                </div>
            </div>

            <div class="compass-container">
                <div class="compass-pointer"></div>
                <div class="compass-scale" id="compass-scale"></div>
            </div>
        </div>

        <!-- Panel Kanan: Status Penerbangan -->
        <div class="side-panel">
            <div class="hud-title">Mission Status</div>
            
            <div class="data-box status-box">
                <div class="data-label">Flight Mode</div>
                <div class="status-text" id="val-mode">UNKNOWN</div>
            </div>
            
            <div class="data-box status-box">
                <div class="data-label">Current Task</div>
                <div class="status-text" id="val-state" style="font-size: 0.9rem;">INIT</div>
            </div>

            <div class="data-box">
                <div class="data-label">Roll</div>
                <div class="data-value" id="val-roll">0.0&deg;</div>
            </div>
            <div class="data-box">
                <div class="data-label">Pitch</div>
                <div class="data-value" id="val-pitch">0.0&deg;</div>
            </div>
            <div class="data-box">
                <div class="data-label">Yaw (Heading)</div>
                <div class="data-value" id="val-yaw">0.0&deg;</div>
            </div>
        </div>
    </div>

    <script>
        // Init Compass Scale
        const compassEl = document.getElementById('compass-scale');
        let compassHTML = '';
        const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
        for(let i=0; i<=720; i+=15) { // Bikin scale lebar biar gampang geser (2x 360)
            let deg = i % 360;
            let isMajor = (deg % 45 === 0);
            let label = isMajor ? dirs[deg / 45] : deg;
            let cls = isMajor ? 'compass-tick major' : 'compass-tick';
            compassHTML += `<div class="${cls}">${label}</div>`;
        }
        compassEl.innerHTML = compassHTML;

        // Init Pitch Scale
        const pitchEl = document.getElementById('pitch-scale');
        let pitchHTML = '';
        for(let i=90; i>=-90; i-=10) {
            let cls = (i === 0) ? 'pitch-line long' : 'pitch-line';
            pitchHTML += `<div class="${cls}"></div>`;
        }
        pitchEl.innerHTML = pitchHTML;

        function radToDeg(rad) {
            return rad * (180.0 / Math.PI);
        }

        function updateHUD() {
            fetch('/api/data')
            .then(res => res.json())
            .then(data => {
                document.getElementById('val-lat').innerText = data.lat.toFixed(7);
                document.getElementById('val-lon').innerText = data.lon.toFixed(7);
                document.getElementById('val-alt').innerText = data.alt.toFixed(1) + ' m';
                
                let modeEl = document.getElementById('val-mode');
                modeEl.innerText = data.mode;
                if(data.mode !== 'GUIDED') modeEl.classList.add('alert-blink');
                else modeEl.classList.remove('alert-blink');

                document.getElementById('val-state').innerText = data.state_str;

                let r_deg = radToDeg(data.roll);
                let p_deg = radToDeg(data.pitch);
                
                document.getElementById('val-roll').innerHTML = r_deg.toFixed(1) + '&deg;';
                document.getElementById('val-pitch').innerHTML = p_deg.toFixed(1) + '&deg;';
                document.getElementById('val-yaw').innerHTML = data.yaw.toFixed(1) + '&deg;';

                // Update Horizon
                let ground = document.getElementById('horizon-ground');
                let pitchScaleEl = document.getElementById('pitch-scale');
                // Translasi pitch (1 derajat pitch = sekitar 3px geser Y)
                let pitchOffset = p_deg * 3;
                // Rotasi roll
                ground.style.transform = `rotate(${-r_deg}deg) translateY(${pitchOffset}px)`;
                pitchScaleEl.style.transform = `translateX(-50%) rotate(${-r_deg}deg) translateY(${pitchOffset}px)`;

                // Update Compass
                // 1 tick (15 deg) = 40px width
                let pxPerDeg = 40 / 15;
                let offsetDeg = data.yaw;
                // Supaya loop mulus kita offset dari tengah
                let totalOffset = - (offsetDeg * pxPerDeg); 
                compassEl.style.transform = `translateX(calc(50% - 20px + ${totalOffset}px))`;

                // Update Battery
                let bat = data.battery;
                let batTxt = document.getElementById('batt-txt');
                let batFill = document.getElementById('batt-fill');
                
                if (bat < 0) {
                    batTxt.innerText = '--%';
                    batFill.style.width = '0%';
                } else {
                    batTxt.innerText = bat + '%';
                    batFill.style.width = bat + '%';
                    if (bat > 50) batFill.style.background = '#00ff88';
                    else if (bat > 20) batFill.style.background = '#ffcc00';
                    else {
                        batFill.style.background = '#ff3366';
                        batTxt.classList.add('alert-blink');
                    }
                    if (bat >= 20) batTxt.classList.remove('alert-blink');
                }
            })
            .catch(err => console.log(err));
        }

        setInterval(updateHUD, 200); // Update 5x/detik
    </script>
</body>
</html>
"""

@app.route('/komponen/<path:filename>')
def serve_komponen(filename):
    return send_from_directory(KOMPONEN_DIR, filename)

@app.route('/')
def index():
    team = shared_data.get('team', 'Biru')
    bg_image = '/komponen/tim-biru/image.png' if team == 'Biru' else '/komponen/tim-merah/image.png'
    return render_template_string(HTML_TEMPLATE, bg_image=bg_image)

@app.route('/api/data')
def api_data():
    return jsonify(shared_data)

def run_server(port):
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def start_dashboard(team="Biru", port=5001):
    shared_data['team'] = team
    print(f"🚀 Memulai HUD Web Dashboard di port {port}...")
    t = threading.Thread(target=run_server, args=(port,), daemon=True)
    t.start()

def update_dashboard(mode=None, state_str=None, lat=None, lon=None, alt=None, yaw=None, roll=None, pitch=None, battery=None):
    if mode is not None: shared_data['mode'] = mode
    if state_str is not None: shared_data['state_str'] = state_str
    if lat is not None: shared_data['lat'] = lat
    if lon is not None: shared_data['lon'] = lon
    if alt is not None: shared_data['alt'] = alt
    if yaw is not None: shared_data['yaw'] = yaw
    if roll is not None: shared_data['roll'] = roll
    if pitch is not None: shared_data['pitch'] = pitch
    if battery is not None: shared_data['battery'] = battery
