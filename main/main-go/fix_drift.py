import os
import re

FILES = [
    "home-wp1.py",
    "wp1-wp2.py",
    "wp2-wp3.py",
    "wp3-wp4.py",
    "wp4-wp5.py"
]

GOTO_GPS_NEW = """def goto_gps_position(master, lat, lon, alt, yaw_deg=None):
    \"\"\"Kirim target posisi GPS. Kecepatan diatur via send_change_speed().\"\"\"
    if master is None: return
    
    if yaw_deg is None:
        type_mask = 0b0000111111111000  # Abaikan yaw
        yaw_rad = 0.0
    else:
        type_mask = 0b0000101111111000  # Gunakan yaw (bit 10=0)
        yaw_rad = 0.0 if yaw_deg is None else __import__('math').radians(yaw_deg)

    master.mav.set_position_target_global_int_send(
        0, master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        type_mask,
        int(lat * 1e7),
        int(lon * 1e7),
        alt,
        0, 0, 0, 0, 0, 0,
        yaw_rad, 0
    )
"""

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # 1. Replace goto_gps_position
    content = re.sub(
        r"def goto_gps_position\(master, lat, lon, alt\):.*?0, 0, 0, 0, 0, 0, 0, 0\n    \)\n",
        GOTO_GPS_NEW,
        content,
        flags=re.DOTALL
    )
    
    def repl_goto_gps(match):
        text = match.group(0)
        
        # Inject yaw_diff calculation
        text = text.replace(
            "arrival_dist = 2.0 if use_aruco else 0.05",
            "arrival_dist = 2.0 if use_aruco else 0.05\n                            yaw_diff = get_shortest_yaw_diff(cur_yaw, bearing) if cur_yaw else 999.0"
        )
        
        # Change condition
        text = text.replace(
            "if dist < arrival_dist:",
            "if dist < arrival_dist and yaw_diff < 15.0:"
        )
        
        # Add yaw_deg=bearing
        text = text.replace(
            "goto_gps_position(master, wp_target['lat'], wp_target['lon'], target_alt)",
            "goto_gps_position(master, wp_target['lat'], wp_target['lon'], target_alt, yaw_deg=bearing)"
        )
        
        return text

    content = re.sub(
        r"                            arrival_dist = 2.0 if use_aruco else 0.05\n.*?last_gps_cmd_time = time\.time\(\)\n",
        repl_goto_gps,
        content,
        flags=re.DOTALL
    )

    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Refactored {filepath}")

for filename in FILES:
    filepath = os.path.join("/home/aris/Dokumen/projeck/krti/vtol-krti/main/main-go", filename)
    if os.path.exists(filepath):
        process_file(filepath)
    else:
        print(f"File not found: {filepath}")
