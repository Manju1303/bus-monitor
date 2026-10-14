"""
create_sample_footage.py
------------------------
Generates a realistic CCTV campus gate surveillance video in footage/sample_bus_gate.mp4
simulating a college transit bus arriving at the gate with license plate 'TN36M3915'.
"""

import os
import cv2
import numpy as np


def prepare_bus_asset(plate_text: str = "TN36 M 3915"):
    """Prepare a realistic bus sprite with the specified license plate."""
    asset_path = os.path.join(os.path.dirname(__file__), "footage", "assets", "bus_only.png")
    if os.path.exists(asset_path):
        bus = cv2.imread(asset_path)
    else:
        # Generate clean bus graphic if asset is missing
        bus = np.full((320, 320, 3), (30, 190, 235), dtype=np.uint8)

    bh, bw = bus.shape[:2]

    # Clean bumper license plate with high-contrast bold lettering
    pw, ph = int(bw * 0.35), int(bh * 0.11)
    px1 = int((bw - pw) / 2)
    py1 = int(bh * 0.80)
    px2 = px1 + pw
    py2 = py1 + ph

    plate = np.ones((ph, pw, 3), dtype=np.uint8) * 255
    cv2.rectangle(plate, (0, 0), (pw - 1, ph - 1), (0, 0, 0), 3)
    cv2.putText(plate, plate_text, (10, int(ph * 0.72)), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (0, 0, 0), 3)

    bus[py1:py2, px1:px2] = plate
    return bus


def generate_sample_cctv_video(output_path="footage/sample_bus_gate.mp4", num_frames=100, plate_no="TN36 M 3915"):
    """
    Generate realistic CCTV surveillance footage of a campus bus crossing the gate threshold.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bus_img = prepare_bus_asset(plate_no)

    width, height = 640, 480
    fps = 20
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    gate_y = 240

    for i in range(num_frames):
        t = i / float(num_frames - 1)
        
        # Asphalt road background with realistic pavement texture
        frame = np.full((height, width, 3), 60, dtype=np.uint8)
        
        # Campus green curbs / sidewalks
        frame[:, :60] = [50, 90, 50]
        frame[:, width - 60:] = [50, 90, 50]
        
        # Yellow curb borders
        cv2.line(frame, (60, 0), (60, height), (0, 200, 240), 2)
        cv2.line(frame, (width - 60, 0), (width - 60, height), (0, 200, 240), 2)

        # Center dashed road markings
        for ly in range(0, height, 40):
            cv2.line(frame, (width // 2, ly), (width // 2, ly + 20), (180, 180, 180), 2)

        # Virtual gate threshold boundary markings
        cv2.line(frame, (60, gate_y), (width - 60, gate_y), (255, 255, 255), 1)
        cv2.putText(frame, "GATE THRESHOLD LINE", (70, gate_y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)

        # CCTV camera live status and timestamp
        cv2.putText(frame, f"CAM-01 [LIVE] FRAME {i:03d} - JKKM MAIN GATE", (15, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 0), 1)

        # Smooth perspective scaling (bus approaches from distance: 0.36 to 0.62)
        scale = 0.36 + (0.62 - 0.36) * t
        cur_w = int(width * scale)
        cur_h = int(height * scale)
        resized = cv2.resize(bus_img, (cur_w, cur_h))

        cur_x = int((width - cur_w) / 2)
        start_y = 10
        end_y = height - cur_h - 10
        cur_y = int(start_y + (end_y - start_y) * t)

        # Compose bus onto frame
        y1 = max(0, cur_y)
        y2 = min(height, cur_y + cur_h)
        x1 = max(0, cur_x)
        x2 = min(width, cur_x + cur_w)

        by1 = y1 - cur_y
        by2 = by1 + (y2 - y1)
        bx1 = x1 - cur_x
        bx2 = bx1 + (x2 - x1)

        frame[y1:y2, x1:x2] = resized[by1:by2, bx1:bx2]
        out.write(frame)

    out.release()
    print(f"[SUCCESS] Realistic CCTV video created at: {output_path} (Plate: {plate_no})")


if __name__ == "__main__":
    generate_sample_cctv_video()
