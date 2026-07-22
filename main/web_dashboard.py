import cv2
import time
import threading
from flask import Flask, Response, jsonify, render_template_string

app = Flask(__name__)

# Global variables
current_frame = None
telemetry_data = {}
lock = threading.Lock()

# HTML Template (Inline)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KRTI VTOL Dashboard</title>
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --glass-bg: rgba(255, 255, 255, 0.05);
            --glass-border: rgba(255, 255, 255, 0.1);
            --primary-accent: #00ff88;
            --secondary-accent: #00b8ff;
            --text-main: #ffffff;
            --text-muted: #8b9bb4;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(0, 255, 136, 0.15) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(0, 184, 255, 0.15) 0px, transparent 50%);
            color: var(--text-main);
            margin: 0;
            padding: 40px 20px;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        h1 {
            font-size: 2.5rem;
            margin-bottom: 30px;
            text-align: center;
            background: linear-gradient(90deg, var(--primary-accent), var(--secondary-accent));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 4px 20px rgba(0,255,136,0.2);
            letter-spacing: 1px;
        }

        .container {
            display: flex;
            flex-direction: row;
            gap: 30px;
            width: 100%;
            max-width: 1200px;
            justify-content: center;
            flex-wrap: wrap;
        }

        /* Glassmorphism Panel */
        .glass-panel {
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            padding: 25px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }

        .glass-panel:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.4);
        }

        .video-wrapper {
            flex: 1 1 600px;
            display: flex;
            flex-direction: column;
        }

        .video-container {
            border-radius: 15px;
            overflow: hidden;
            position: relative;
            background: #000;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 480px;
            border: 1px solid rgba(255,255,255,0.05);
        }

        .video-container::after {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            box-shadow: inset 0 0 20px rgba(0,0,0,0.8);
            pointer-events: none;
        }

        img {
            width: 100%;
            height: auto;
            object-fit: cover;
            display: block;
        }

        .telemetry-wrapper {
            flex: 1 1 400px;
            display: flex;
            flex-direction: column;
        }

        .telemetry-header {
            font-size: 1.5rem;
            font-weight: 500;
            margin-top: 0;
            margin-bottom: 20px;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .pulse {
            width: 10px;
            height: 10px;
            background-color: var(--primary-accent);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--primary-accent);
            animation: pulse-animation 1.5s infinite;
        }

        @keyframes pulse-animation {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 136, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(0, 255, 136, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 136, 0); }
        }

        .telemetry-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
        }

        .telemetry-card {
            background: rgba(0,0,0,0.2);
            border: 1px solid rgba(255,255,255,0.05);
            padding: 15px 20px;
            border-radius: 12px;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .telemetry-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: linear-gradient(to bottom, var(--primary-accent), var(--secondary-accent));
            border-radius: 4px 0 0 4px;
        }

        .telemetry-card:hover {
            background: rgba(255,255,255,0.05);
            transform: scale(1.02);
        }

        .telemetry-title {
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
            font-weight: 500;
        }

        .telemetry-value {
            font-size: 1.4rem;
            font-weight: 700;
            color: var(--text-main);
            text-shadow: 0 2px 4px rgba(0,0,0,0.5);
        }

        /* Status card highlight for important states */
        .status-card {
            grid-column: 1 / -1;
            background: linear-gradient(135deg, rgba(0,255,136,0.1), rgba(0,184,255,0.1));
            border-color: rgba(0,255,136,0.2);
        }
        .status-card .telemetry-value {
            color: var(--primary-accent);
        }

        @media (max-width: 768px) {
            .container { flex-direction: column; }
            .video-container { min-height: 300px; }
        }
    </style>
    <script>
        function updateTelemetry() {
            fetch('/telemetry')
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('telemetry-grid');
                    container.innerHTML = '';
                    for (const [key, value] of Object.entries(data)) {
                        const card = document.createElement('div');
                        
                        // Make Status card span full width and highlight it
                        if (key.toLowerCase() === 'status') {
                            card.className = 'telemetry-card status-card';
                        } else {
                            card.className = 'telemetry-card';
                        }
                        
                        const title = document.createElement('div');
                        title.className = 'telemetry-title';
                        title.innerText = key;
                        
                        const val = document.createElement('div');
                        val.className = 'telemetry-value';
                        val.innerText = value;
                        
                        // Change color based on specific values if needed
                        if (key.toLowerCase() === 'status' && value.includes('TERKUNCI')) {
                            val.style.color = '#ffff00'; // Yellow for locked
                            card.style.background = 'linear-gradient(135deg, rgba(255,255,0,0.1), rgba(255,150,0,0.1))';
                            card.style.borderColor = 'rgba(255,255,0,0.3)';
                        }
                        
                        card.appendChild(title);
                        card.appendChild(val);
                        container.appendChild(card);
                    }
                })
                .catch(err => console.error(err));
        }
        // Update telemetry frequently for responsiveness
        setInterval(updateTelemetry, 250);
    </script>
</head>
<body>
    <h1>🛸 Live Flight Telemetry</h1>
    <div class="container">
        <div class="glass-panel video-wrapper">
            <div class="telemetry-header">
                <div class="pulse"></div> Live Camera Feed
            </div>
            <div class="video-container">
                <img src="/video_feed" alt="Video Stream">
            </div>
        </div>
        <div class="glass-panel telemetry-wrapper">
            <div class="telemetry-header">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--primary-accent);"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                Flight Status
            </div>
            <div id="telemetry-grid" class="telemetry-grid">
                <p style="color: var(--text-muted); text-align: center; width: 100%;">Menunggu data koneksi...</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

def generate_frames():
    global current_frame, lock
    while True:
        with lock:
            if current_frame is None:
                frame_to_encode = None
            else:
                frame_to_encode = current_frame.copy()
        
        if frame_to_encode is None:
            time.sleep(0.1)
            continue
            
        ret, buffer = cv2.imencode('.jpg', frame_to_encode)
        if not ret:
            time.sleep(0.1)
            continue
            
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # Limit to ~20 FPS to reduce CPU load
        time.sleep(0.05)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/telemetry')
def get_telemetry():
    global telemetry_data, lock
    with lock:
        # Return a copy to avoid race conditions during serialization
        return jsonify(telemetry_data.copy())

def _run_flask(port):
    # Disable flask logging
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def start_web_server(port=5000):
    """
    Menjalankan web server Flask di thread terpisah.
    Fungsi ini dipanggil sekali saat inisialisasi.
    """
    print(f"🌍 Memulai Web Dashboard di http://0.0.0.0:{port}")
    server_thread = threading.Thread(target=_run_flask, args=(port,))
    server_thread.daemon = True # Agar thread mati saat program utama selesai
    server_thread.start()

def update_web_data(frame, telemetry):
    """
    Memperbarui frame kamera dan data telemetri yang akan ditampilkan di web.
    Fungsi ini dipanggil di dalam loop utama program (while True).
    
    :param frame: numpy array (gambar dari OpenCV)
    :param telemetry: dictionary berisi data status/telemetri drone
    """
    global current_frame, telemetry_data, lock
    with lock:
        if frame is not None:
            current_frame = frame
        if telemetry is not None:
            telemetry_data = telemetry
