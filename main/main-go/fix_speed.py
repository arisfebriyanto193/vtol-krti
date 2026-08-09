import os
import re

FILES = [
    "home-wp1.py",
    "wp1-wp2.py",
    "wp2-wp3.py",
    "wp3-wp4.py",
    "wp4-wp5.py"
]

NEW_FUNC = """def send_change_speed(master, speed_ms):
    \"\"\"Set kecepatan navigasi drone via MAV_CMD_DO_CHANGE_SPEED dan Parameter.\"\"\"
    if master is None: return
    
    # 1. Cara standar MAVLink (berlaku untuk AUTO mode)
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED, 0,
        1,        # param1: 1 = ground speed
        speed_ms, # param2: kecepatan dalam m/s
        -1, 0, 0, 0, 0
    )
    
    # 2. Cara spesifik ArduCopter untuk GUIDED mode (WPNAV_SPEED dalam cm/s)
    master.mav.param_set_send(
        master.target_system, master.target_component,
        b'WPNAV_SPEED',
        speed_ms * 100.0,
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32
    )
"""

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    content = re.sub(
        r"def send_change_speed\(master, speed_ms\):.*?        -1, 0, 0, 0, 0\n    \)\n",
        NEW_FUNC,
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
