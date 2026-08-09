import os
import sys
import subprocess
import signal
from flask import Flask, render_template_string, jsonify, request

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MISSIONS = {
    'wp1-wp2': {'script': 'wp1-wp2.py', 'port': 5001, 'name': 'Navigasi WP1 -> WP2'},
    'wp2-wp3': {'script': 'wp2-wp3.py', 'port': 5002, 'name': 'Navigasi WP2 -> WP3'},
    'wp3-wp4': {'script': 'wp3-wp4.py', 'port': 5003, 'name': 'Navigasi WP3 -> WP4'},
    'wp4-wp5': {'script': 'wp4-wp5.py', 'port': 5004, 'name': 'Navigasi WP4 -> WP5 (Landing)'}
}

current_process = None
current_mission = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KRTI VTOL - Mission Control</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;500;700;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-accent: #00ff88;
            --secondary-accent: #00b8ff;
            --bg-color: #0b0f19;
            --panel-bg: rgba(255, 255, 255, 0.05);
            --text-main: #ffffff;
        }
        body {
            font-family: 'Outfit', sans-serif;
            margin: 0; padding: 0;
            background-color: var(--bg-color);
            color: var(--text-main);
            display: flex;
            height: 100vh;
            overflow: hidden;
        }
        .sidebar {
            width: 320px;
            background: rgba(0,0,0,0.8);
            border-right: 1px solid rgba(255,255,255,0.1);
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
            z-index: 100;
        }
        .main-content {
            flex-grow: 1;
            position: relative;
            display: flex;
            justify-content: center;
            align-items: center;
            background: #000;
        }
        h2 {
            margin: 0 0 20px 0;
            text-align: center;
            color: var(--secondary-accent);
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 15px;
        }
        .mission-btn {
            background: var(--panel-bg);
            border: 1px solid rgba(255,255,255,0.2);
            color: white;
            padding: 15px;
            border-radius: 8px;
            cursor: pointer;
            font-family: 'Outfit', sans-serif;
            font-size: 1rem;
            font-weight: 500;
            transition: 0.3s;
            text-align: left;
        }
        .mission-btn:hover {
            background: rgba(0,184,255,0.2);
            border-color: var(--secondary-accent);
        }
        .mission-btn.active {
            background: rgba(0,255,136,0.2);
            border-color: var(--primary-accent);
            box-shadow: 0 0 15px rgba(0,255,136,0.3);
        }
        
        .controls {
            margin-top: auto;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .btn-stop {
            background: #ff3366;
            color: white;
            border: none;
            padding: 15px;
            border-radius: 8px;
            font-weight: 700;
            cursor: pointer;
            text-align: center;
            font-size: 1.1rem;
            transition: 0.3s;
        }
        .btn-stop:hover {
            background: #e60039;
            box-shadow: 0 0 15px rgba(255,51,102,0.4);
        }
        
        .status-indicator {
            padding: 10px;
            text-align: center;
            border-radius: 8px;
            background: rgba(255,255,255,0.1);
            font-weight: bold;
        }
        .status-running { background: rgba(0,255,136,0.2); color: var(--primary-accent); }
        .status-stopped { background: rgba(255,51,102,0.2); color: #ff3366; }

        iframe {
            width: 100%;
            height: 100%;
            border: none;
            display: none;
            background: transparent;
        }
        .standby-screen {
            position: absolute;
            font-size: 2.5rem;
            color: rgba(255,255,255,0.2);
            text-transform: uppercase;
            letter-spacing: 5px;
            font-weight: 900;
            text-align: center;
        }
        .standby-screen span {
            display: block;
            font-size: 1rem;
            font-weight: 300;
            margin-top: 10px;
            letter-spacing: 2px;
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <h2>🚀 Mission Control</h2>
        
        <div id="mission-list">
            <!-- Buttons rendered here -->
        </div>

        <div class="controls">
            <div id="status-box" class="status-indicator status-stopped">STATUS: STOPPED</div>
            <button class="btn-stop" onclick="stopMission()">🛑 STOP ALL</button>
        </div>
    </div>
    
    <div class="main-content">
        <div id="standby" class="standby-screen">
            SYSTEM STANDBY
            <span>Pilih misi pada panel kontrol untuk memulai</span>
        </div>
        <iframe id="hud-frame" src=""></iframe>
    </div>

    <script>
        const missions = {
            'wp1-wp2': 'Navigasi WP1 -> WP2',
            'wp2-wp3': 'Navigasi WP2 -> WP3',
            'wp3-wp4': 'Navigasi WP3 -> WP4',
            'wp4-wp5': 'Navigasi WP4 -> WP5 (Landing)'
        };

        function renderButtons(activeId) {
            let html = '';
            for(let id in missions) {
                let activeClass = (id === activeId) ? 'active' : '';
                html += `<button class="mission-btn ${activeClass}" onclick="startMission('${id}')">▶ ${missions[id]}</button>`;
            }
            document.getElementById('mission-list').innerHTML = html;
        }

        function startMission(id) {
            fetch('/api/start/' + id, {method: 'POST'})
            .then(res => res.json())
            .then(data => {
                if(data.status === 'success') {
                    // Kasih delay dikit biar server python yang baru bisa up
                    setTimeout(checkStatus, 1500); 
                } else {
                    alert('Error: ' + data.message);
                }
            });
        }

        function stopMission() {
            fetch('/api/stop', {method: 'POST'})
            .then(() => checkStatus());
        }

        function checkStatus() {
            fetch('/api/status')
            .then(res => res.json())
            .then(data => {
                renderButtons(data.running);
                
                let sbox = document.getElementById('status-box');
                let frame = document.getElementById('hud-frame');
                let standby = document.getElementById('standby');

                if (data.running) {
                    sbox.innerText = 'STATUS: RUNNING ' + data.running.toUpperCase();
                    sbox.className = 'status-indicator status-running';
                    
                    let targetUrl = `http://${window.location.hostname}:${data.port}`;
                    if (frame.src !== targetUrl) {
                        frame.src = targetUrl;
                    }
                    frame.style.display = 'block';
                    standby.style.display = 'none';
                } else {
                    sbox.innerText = 'STATUS: STOPPED';
                    sbox.className = 'status-indicator status-stopped';
                    frame.src = '';
                    frame.style.display = 'none';
                    standby.style.display = 'block';
                }
            });
        }

        // Initialize
        checkStatus();
        setInterval(checkStatus, 2000); // Poll status every 2 seconds
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/status')
def status():
    global current_process, current_mission
    
    # Cek apakah proses mati sendiri atau telah selesai
    if current_process is not None:
        if current_process.poll() is not None:
            current_process = None
            current_mission = None
            
    if current_mission:
        return jsonify({
            "running": current_mission,
            "port": MISSIONS[current_mission]['port']
        })
    return jsonify({"running": None, "port": None})

@app.route('/api/start/<mission_id>', methods=['POST'])
def start_mission(mission_id):
    global current_process, current_mission
    
    if mission_id not in MISSIONS:
        return jsonify({"status": "error", "message": "Mission ID tidak valid"})
        
    # Hentikan misi yang sedang berjalan
    if current_process is not None:
        try:
            os.kill(current_process.pid, signal.SIGTERM)
            current_process.wait(timeout=2)
        except:
            pass
            
    script_path = os.path.join(BASE_DIR, MISSIONS[mission_id]['script'])
    
    # Jalankan sebagai subprocess
    print(f"🚀 Memulai misi {mission_id}...")
    current_process = subprocess.Popen([sys.executable, script_path], cwd=BASE_DIR)
    current_mission = mission_id
    
    return jsonify({"status": "success", "port": MISSIONS[mission_id]['port']})

@app.route('/api/stop', methods=['POST'])
def stop_mission():
    global current_process, current_mission
    if current_process is not None:
        print("🛑 Menghentikan misi...")
        try:
            os.kill(current_process.pid, signal.SIGTERM)
            current_process.wait(timeout=2)
        except:
            pass
        current_process = None
        current_mission = None
    return jsonify({"status": "success"})

if __name__ == '__main__':
    print("🚀 Memulai Web App Launcher & Mission Control di port 8080...")
    app.run(host='0.0.0.0', port=8080, debug=False)