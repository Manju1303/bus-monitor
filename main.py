"""
main.py - CLI Pipeline Integration for Bus Gate Monitoring System
-------------------------------------------------------------------
Integrates YOLOv8 detection, EasyOCR license plate recognition, spatial vehicle
tracking, multi-frame plate voting, JPEG snapshot capturing, and SQLite logging into a CLI pipeline.

Usage:
    python main.py                          # Uses footage in footage/ folder
    python main.py footage/cctv_bus.mp4     # Custom video file path
    python main.py 0                        # Live webcam stream
    python main.py rtsp://192.168.1.100/1   # RTSP CCTV stream
"""

import os
import sys
import time
import cv2
import numpy as np
from collections import Counter

from detector import BusDetector
from ocr import PlateReader
from tracker import VehicleTracker
from database import GateDatabase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(BASE_DIR, "static", "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def resolve_video_source(source_arg=None):
    """Resolve video source argument to an opened VideoCapture or valid default file."""
    if source_arg is not None:
        if str(source_arg).isdigit():
            return cv2.VideoCapture(int(source_arg)), f"Webcam ({source_arg})"
        if os.path.exists(source_arg) or str(source_arg).startswith(("rtsp://", "http://")):
            return cv2.VideoCapture(source_arg), str(source_arg)

    # Fallback to footage/ directory
    footage_dir = os.path.join(BASE_DIR, "footage")
    if os.path.isdir(footage_dir):
        for f in sorted(os.listdir(footage_dir)):
            if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
                fpath = os.path.join(footage_dir, f)
                return cv2.VideoCapture(fpath), fpath

    print("[ERROR] No video source found. Provide a video file argument or place video files in footage/.")
    return None, None


def run_bus_monitoring_system(source_arg=None, display_window: bool = True):
    """
    Run the Bus Gate Entry & Exit Monitoring pipeline.

    :param source_arg: Video file path, camera index (0), or RTSP URL
    :param display_window: Show interactive OpenCV GUI window
    """
    print("=========================================================")
    print(" 🚌 CAMPUS BUS GATE MONITORING PIPELINE ")
    print("=========================================================")

    # 1. Initialize Pipeline Modules
    detector = BusDetector(confidence=0.35)
    ocr_reader = PlateReader(gpu=False)
    tracker = VehicleTracker(gate_line_y=250)
    logger = GateDatabase("bus_gate.db")

    # 2. Open Video Stream
    cap, source_name = resolve_video_source(source_arg)
    if cap is None or not cap.isOpened():
        print(f"[ERROR] Unable to open video source: {source_name}")
        return

    print(f"[INFO] Monitoring video source: {source_name}")
    print("[INFO] Press 'q' on video window to stop.")

    # Multi-frame plate voting cache: vehicle_id -> list of OCR readings
    plate_votes = {}

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("[INFO] Video feed ended or final frame reached.")
            break

        frame_h, frame_w, _ = frame.shape
        gate_line_y = int(frame_h * 0.5)
        tracker.gate_line_y = gate_line_y

        # A. Detect Buses
        detections = detector.detect(frame)

        # B. Update Vehicle Centroid Tracking
        tracking_results = tracker.update(detections)

        # Draw Gate Boundary Line
        cv2.line(frame, (0, gate_line_y), (frame_w, gate_line_y), (0, 0, 255), 3)
        cv2.putText(frame, "GATE ENTRY / EXIT THRESHOLD", (15, gate_line_y - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)

        # C. Process Detections & Collect OCR Votes
        for det in detections:
            box = det['box']
            x1, y1, x2, y2 = box

            det_cx = int((x1 + x2) / 2.0)
            det_cy = int((y1 + y2) / 2.0)
            matched_id = None
            best_dist = float('inf')

            for veh_id, info in tracking_results.items():
                tx, ty = info["centroid"]
                dist = ((det_cx - tx) ** 2 + (det_cy - ty) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    matched_id = veh_id

            if matched_id is not None:
                roi = detector.crop_plate_region(frame, box)
                plate_text, _ = ocr_reader.read_plate(roi)
                if plate_text:
                    if matched_id not in plate_votes:
                        plate_votes[matched_id] = []
                    plate_votes[matched_id].append(plate_text)

            # Resolve current most frequent plate string
            display_plate = "READING..."
            if matched_id and matched_id in plate_votes and plate_votes[matched_id]:
                display_plate = Counter(plate_votes[matched_id]).most_common(1)[0][0]

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"Bus ({det['confidence']})", (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

            if display_plate != "READING...":
                cv2.putText(frame, f"PLATE: {display_plate}", (x1, y2 + 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        # D. Check for Line Crossing Events
        for veh_id, info in tracking_results.items():
            cx, cy = info["centroid"]
            direction = info["direction"]

            if veh_id in plate_votes and plate_votes[veh_id]:
                plate_no = Counter(plate_votes[veh_id]).most_common(1)[0][0]
            else:
                plate_no = "UNKNOWN"

            cv2.circle(frame, (cx, cy), 6, (255, 0, 0), -1)
            cv2.putText(frame, f"ID #{veh_id}", (cx + 10, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

            if direction and not info["is_logged"]:
                # Save JPEG Snapshot Evidence
                snap_filename = f"snap_bus_{veh_id}_{int(time.time())}.jpg"
                snap_filepath = os.path.join(SNAPSHOT_DIR, snap_filename)
                cv2.imwrite(snap_filepath, frame)

                # Log to SQLite DB
                logger.log_vehicle(veh_id, plate_no, direction, snapshot=snap_filename)
                tracker.logged_vehicles.add(veh_id)

                print(f"[EVENT] LOGGED: {plate_no} -> {direction.upper()} (Saved snapshot: {snap_filename})")

                # Visual Event Alert
                alert_text = f"LOGGED: {plate_no} ({direction.upper()})"
                cv2.putText(frame, alert_text, (20, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 255), 3)

        if display_window:
            try:
                cv2.imshow("Campus Bus Monitoring System", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            except Exception:
                pass

    cap.release()
    cv2.destroyAllWindows()
    print("[SUCCESS] Monitoring pipeline execution completed.")


if __name__ == "__main__":
    arg_source = sys.argv[1] if len(sys.argv) > 1 else None
    run_bus_monitoring_system(arg_source)
