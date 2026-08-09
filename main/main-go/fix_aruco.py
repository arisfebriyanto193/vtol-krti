import os
import re

FILES = [
    "home-wp1.py",
    "wp2-wp3.py",
    "wp3-wp4.py",
    "wp4-wp5.py"
]

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Replace the conditional and logic
    content = content.replace(
        "if ids is not None and TARGET_ID in ids:\n                        idx = np.where(ids == TARGET_ID)[0][0]",
        "if ids is not None and len(ids) > 0:\n                        idx = 0\n                        detected_id = ids[idx][0]"
    )
    
    # Replace the drawing
    content = content.replace(
        "cv2.aruco.drawDetectedMarkers(display_frame, [corners[idx]], np.array([[TARGET_ID]]))",
        "cv2.aruco.drawDetectedMarkers(display_frame, [corners[idx]], np.array([[detected_id]]))"
    )

    # Replace the text overlay
    content = re.sub(
        r"cv2\.putText\(display_frame, f\"MENCARI ARUCO ID \{TARGET_ID\}\.\.\.\",",
        'cv2.putText(display_frame, "MENCARI ARUCO...",',
        content
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
