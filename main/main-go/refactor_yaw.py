import os
import re

FILES = [
    "home-wp1.py",
    "wp1-wp2.py",
    "wp2-wp3.py",
    "wp3-wp4.py",
    "wp4-wp5.py"
]

GET_BEARING_FUNC = """def get_bearing(lat1, lon1, lat2, lon2):
    dLon = math.radians(lon2 - lon1)
    y = math.sin(dLon) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \\
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dLon)
    bearing = math.atan2(y, x)
    return (math.degrees(bearing) + 360) % 360

"""

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # 1. Insert get_bearing after get_shortest_yaw_diff
    if "def get_bearing" not in content:
        content = re.sub(
            r"(def get_shortest_yaw_diff.*?return abs\(diff\)\n)",
            r"\1\n" + GET_BEARING_FUNC,
            content,
            flags=re.DOTALL
        )

    # 2. Modify STATE_INIT to go directly to STATE_GOTO_GPS and use bearing
    state_init_pattern = re.compile(
        r"(\s+if state == STATE_INIT:.*?)(?=\s+elif state == STATE_ROTATE_YAW:)",
        re.DOTALL
    )
    
    def repl_state_init(match):
        return """                if state == STATE_INIT:
                    if cur_yaw is None or cur_lat is None or cur_lon is None:
                        if time.time() - last_log_time > 1.0:
                            log_msg("Menunggu data telemetry Yaw/GPS dari Pixhawk...", "WAIT")
                            last_log_time = time.time()
                    else:
                        bearing = get_bearing(cur_lat, cur_lon, wp_target['lat'], wp_target['lon'])
                        log_msg(f"Mode GUIDED aktif. Naik ke {target_alt}m & Yaw ke {bearing:.1f} deg sambil maju.", "ACTION")
                        send_change_speed(master, drone_speed)
                        goto_gps_position(master, wp_target['lat'], wp_target['lon'], target_alt)
                        rotate_to_yaw(master, cur_yaw, bearing)
                        last_yaw_cmd_time = time.time()
                        last_gps_cmd_time = time.time()
                        state = STATE_GOTO_GPS
"""
    
    content = state_init_pattern.sub(repl_state_init, content)

    # 3. Remove STATE_ROTATE_YAW and STATE_WAIT_ALT completely
    # They span from `elif state == STATE_ROTATE_YAW:` to `elif state == STATE_GOTO_GPS:`
    remove_pattern = re.compile(
        r"(\s+elif state == STATE_ROTATE_YAW:.*?)(\s+elif state == STATE_GOTO_GPS:)",
        re.DOTALL
    )
    content = remove_pattern.sub(r"\2", content)

    # 4. In the telemetry print at the bottom, change TgtYaw to Bearing
    # Search for: f"Mode={mode} | State={state_str} | TgtYaw={wp_target['yaw']:.1f}
    # We'll just leave TgtYaw as it was (from wp_target['yaw']), because bearing isn't global.
    
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Refactored {filepath}")

for filename in FILES:
    filepath = os.path.join("/home/aris/Dokumen/projeck/krti/vtol-krti/main/main-go", filename)
    if os.path.exists(filepath):
        process_file(filepath)
    else:
        print(f"File not found: {filepath}")
