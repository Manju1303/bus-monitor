"""
create_sample_footage.py
------------------------
Generates a sample CCTV video in footage/sample_bus_gate.mp4
simulating a campus gate with an arriving bus displaying plate 'TN38AB1234'.
"""

import os
import cv2
import numpy as np

def generate_sample_cctv_video(output_path="footage/sample_bus_gate.mp4", num_frames=120):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    width, height = 640, 480
    fps = 20
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    gate_y = 240
    bus_w, bus_h = 220, 160
    
    # Bus starts above gate and moves down across the gate line
    start_y = 60
    end_y = 300
    
    for i in range(num_frames):
        # Progress 0.0 -> 1.0
        t = i / float(num_frames)
        curr_y = int(start_y + (end_y - start_y) * t)
        curr_x = int(width / 2 - bus_w / 2)
        
        # Background: asphalt road with pavement markings
        frame = np.full((height, width, 3), 70, dtype=np.uint8)
        
        # Road borders (grass / sidewalk)
        frame[:, :80] = [60, 100, 60]
        frame[:, width - 80:] = [60, 100, 60]
        
        # Gate line markings
        cv2.line(frame, (80, gate_y), (width - 80, gate_y), (255, 255, 255), 2)
        cv2.putText(frame, "CAMPUS GATE LINE", (90, gate_y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
        
        # Timestamp overlay (CCTV style)
        cv2.putText(frame, f"CAM-01 [LIVE] FRAME {i:03d}", (15, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # Draw Bus Body (College Bus Yellow: BGR ~ [30, 200, 240])
        bx1 = curr_x
        by1 = curr_y
        bx2 = bx1 + bus_w
        by2 = by1 + bus_h
        
        # Shadow
        cv2.rectangle(frame, (bx1 + 10, by2 - 5), (bx2 - 10, by2 + 15), (40, 40, 40), -1)
        
        # Yellow body
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (30, 190, 235), -1)
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (20, 140, 180), 3)
        
        # Windshield
        cv2.rectangle(frame, (bx1 + 20, by1 + 20), (bx2 - 20, by1 + 75), (200, 200, 200), -1)
        cv2.rectangle(frame, (bx1 + 20, by1 + 20), (bx2 - 20, by1 + 75), (50, 50, 50), 2)
        cv2.putText(frame, "CAMPUS BUS", (bx1 + 45, by1 + 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2)
        
        # Headlights
        cv2.circle(frame, (bx1 + 25, by1 + 105), 12, (255, 255, 255), -1)
        cv2.circle(frame, (bx2 - 25, by1 + 105), 12, (255, 255, 255), -1)
        
        # Front Bumper
        cv2.rectangle(frame, (bx1 + 15, by1 + 120), (bx2 - 15, by2 - 5), (50, 50, 50), -1)
        
        # License Plate (White plate with black bold text)
        plate_w, plate_h = 110, 28
        px1 = int((bx1 + bx2) / 2 - plate_w / 2)
        py1 = int(by1 + 122)
        px2 = px1 + plate_w
        py2 = py1 + plate_h
        
        cv2.rectangle(frame, (px1, py1), (px2, py2), (255, 255, 255), -1)
        cv2.rectangle(frame, (px1, py1), (px2, py2), (0, 0, 0), 2)
        cv2.putText(frame, "TN38AB1234", (px1 + 6, py1 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 0, 0), 2)
        
        out.write(frame)
        
    out.release()
    print(f"[SUCCESS] Sample CCTV video created at: {output_path}")

if __name__ == "__main__":
    generate_sample_cctv_video()
