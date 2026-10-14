"""
app.py - Campus Bus Gate Entry & Exit Management System
------------------------------------------------------
Flask web interface for live gate camera monitoring, automated vehicle tracking,
license plate identification, activity log search, SQLite logging, and Excel reporting.
"""

import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

try:
    import torch
    torch.set_num_threads(1)
except Exception:
    pass

import json
import time
import base64
import cv2
import numpy as np
from collections import Counter
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, Response, jsonify, send_file, send_from_directory
)
from werkzeug.utils import secure_filename

from detector import BusDetector
from ocr import PlateReader
from tracker import VehicleTracker
from database import GateDatabase

app = Flask(__name__)
app.secret_key = "campus_bus_gate_security_key_2026"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
SNAPSHOT_FOLDER = os.path.join(BASE_DIR, 'static', 'snapshots')
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
WHITELIST_PATH = os.path.join(BASE_DIR, 'registered_buses.json')

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SNAPSHOT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

# Initialize SQLite Database backend (with Excel export capability)
db_path = os.path.join(BASE_DIR, "bus_gate.db")
excel_export_path = os.path.join(BASE_DIR, "bus_gate_log.xlsx")
logger = GateDatabase(db_path)
logger.seed_sample_records()

from concurrent.futures import ThreadPoolExecutor

# Lazily initialized model instances & asynchronous OCR worker pool
detector = None
ocr_reader = None
tracker = None
ocr_executor = ThreadPoolExecutor(max_workers=2)
ocr_pending_ids = set()


def load_config():
    """Load system configuration from config.json."""
    default_config = {
        "gate_line_y_fraction": 0.5,
        "camera_name": "Gate Camera 01",
        "min_confidence": 0.35
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
                default_config.update(cfg)
        except Exception as e:
            print("[CONFIG ERROR]", e)
    return default_config


def load_whitelist():
    """Load registered buses list from registered_buses.json."""
    if os.path.exists(WHITELIST_PATH):
        try:
            with open(WHITELIST_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            print("[WHITELIST ERROR]", e)
    return {"whitelist": [], "alert_on_unknown": False}


def get_pipeline():
    """Lazily load computer vision detector, OCR reader, and centroid tracker with error protection."""
    global detector, ocr_reader, tracker
    cfg = load_config()
    try:
        if detector is None:
            print("[INFO] Loading vehicle detector...")
            detector = BusDetector(
                confidence=cfg.get("min_confidence", 0.25),
                target_classes=cfg.get("target_classes", [5, 7, 2])
            )
    except Exception as e:
        print(f"[ERROR] Failed to load BusDetector: {e}")
        detector = None

    try:
        if ocr_reader is None:
            print("[INFO] Loading license plate reader...")
            ocr_reader = PlateReader(gpu=False)
    except Exception as e:
        print(f"[ERROR] Failed to load PlateReader: {e}")
        ocr_reader = None

    try:
        if tracker is None:
            print("[INFO] Initializing gate centroid tracker...")
            tracker = VehicleTracker(gate_line_y=250)
    except Exception as e:
        print(f"[ERROR] Failed to load VehicleTracker: {e}")
        tracker = None

    return detector, ocr_reader, tracker


# Global active video source state: 'default_footage', 'webcam', RTSP URL, or file path
current_video_source = "default_footage"
latest_frame_cache = None


def is_allowed_file(filename):
    """Check if uploaded file has a valid video extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_video_capture():
    """Resolve OpenCV VideoCapture stream based on current source selection with Windows DirectShow support."""
    global current_video_source
    import platform

    if current_video_source == "webcam":
        # On Windows, DirectShow (CAP_DSHOW) opens webcams without delay or MSMF locking
        if platform.system() == "Windows":
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
        else:
            cap = cv2.VideoCapture(0)

        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            return cap

        # Try secondary camera index (device 1)
        if platform.system() == "Windows":
            cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(1)

        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            return cap

        print("[WARNING] Live webcam (Camera 0/1) could not be opened.")
        return None

    elif current_video_source.startswith("rtsp://") or current_video_source.startswith("http://"):
        return cv2.VideoCapture(current_video_source)
    else:
        # Check if direct file or relative to BASE_DIR
        candidate = current_video_source
        if not os.path.isabs(candidate):
            candidate = os.path.join(BASE_DIR, candidate)

        if os.path.isfile(candidate):
            cap = cv2.VideoCapture(candidate)
            if cap.isOpened():
                return cap

        # Fallback 1: check for sample_bus_gate.mp4
        sample_path = os.path.join(BASE_DIR, "footage", "sample_bus_gate.mp4")
        if os.path.isfile(sample_path):
            cap = cv2.VideoCapture(sample_path)
            if cap.isOpened():
                return cap

        # Fallback 2: pick first video found in footage/ directory
        footage_dir = os.path.join(BASE_DIR, "footage")
        if os.path.isdir(footage_dir):
            for f in sorted(os.listdir(footage_dir)):
                if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
                    cap = cv2.VideoCapture(os.path.join(footage_dir, f))
                    if cap.isOpened():
                        return cap

        print("[WARNING] No default video found in footage/. Please upload a video.")
        return None


def generate_frames():
    """Video stream frame generator with multi-frame OCR voting, loop auto-reset, and snapshot logging."""
    global latest_frame_cache
    det, ocr, trk = get_pipeline()
    cap = get_video_capture()
    cfg = load_config()
    wlist_data = load_whitelist()
    whitelist = set(wlist_data.get("whitelist", []))

    # Multi-frame plate voting store: vehicle_id -> list of OCR string readings
    plate_votes = {}
    last_source = current_video_source
    frame_idx = 0
    banner_text = ""
    banner_timer = 0

    while True:
        frame_idx += 1
        # Detect video source changes dynamically
        if last_source != current_video_source:
            if cap is not None:
                cap.release()
            cap = get_video_capture()
            last_source = current_video_source
            plate_votes.clear()
            if trk is not None:
                trk.reset()

        if cap is None or not cap.isOpened():
            cap = get_video_capture()
            if cap is None or not cap.isOpened():
                # Branded standby frame with dynamic status
                standby = np.zeros((480, 640, 3), dtype=np.uint8)
                standby[:] = (20, 24, 33)  # Dark slate background
                cv2.rectangle(standby, (20, 20), (620, 460), (37, 99, 235), 2)

                ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if current_video_source == "webcam":
                    cv2.putText(standby, "JKKM GATE SURVEILLANCE - LIVE WEBCAM", (35, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
                    cv2.putText(standby, f"TIME: {ts_str}", (35, 95),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (148, 163, 184), 1)
                    cv2.putText(standby, "STATUS: CAMERA 0 NOT DETECTED / DISCONNECTED", (35, 220),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 165, 255), 2)
                    cv2.putText(standby, "Please plug in a USB camera or switch to CCTV video footage", (35, 260),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 210, 225), 1)
                else:
                    cv2.putText(standby, "JKKM GATE SURVEILLANCE CAM 01 [STANDBY]", (40, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
                    cv2.putText(standby, f"TIME: {ts_str}", (40, 95),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (148, 163, 184), 1)
                    cv2.putText(standby, "STATUS: AWAITING CCTV FOOTAGE / RTSP STREAM", (40, 240),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.58, (235, 140, 50), 2)
                    cv2.putText(standby, "Please upload a video file or select footage from dropdown", (40, 280),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (180, 190, 205), 1)

                success, buffer = cv2.imencode('.jpg', standby)
                if success:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                time.sleep(0.5)
                continue

        ret, frame = cap.read()
        if not ret:
            # Re-seek video to frame 0 for continuous looping & reset tracker for fresh detection
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            if trk is not None:
                trk.reset()
            plate_votes.clear()
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

        # Cache latest clean frame for instant manual capture
        latest_frame_cache = frame.copy()

        frame_h, frame_w, _ = frame.shape
        gate_y = int(frame_h * cfg.get("gate_line_y_fraction", 0.5))
        if trk is not None:
            trk.gate_line_y = gate_y

        # Detect buses and transit vehicles
        detections = det.detect(frame) if det is not None else []

        # Update vehicle centroid tracking
        tracking_results = trk.update(detections) if trk is not None else {}

        # Draw Campus Gate Line
        cv2.line(frame, (0, gate_y), (frame_w, gate_y), (0, 0, 255), 2)
        cv2.putText(frame, f"GATE THRESHOLD ({cfg.get('camera_name', 'Gate Cam')})", (15, gate_y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # Match detection bounding boxes to vehicle IDs and collect OCR votes
        for d in detections:
            box = d['box']
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

            # Non-blocking async OCR reading to keep video stream smooth at 30 FPS
            if matched_id is not None and ocr is not None and det is not None:
                votes = plate_votes.get(matched_id, [])
                if len(votes) < 3 and matched_id not in ocr_pending_ids:
                    roi = det.crop_plate_region(frame, box, lower_fraction=0.6)
                    if roi is not None and roi.size > 0:
                        ocr_pending_ids.add(matched_id)
                        roi_copy = roi.copy()

                        def async_ocr_worker(vid, roi_img):
                            try:
                                p_text, conf = ocr.read_plate(roi_img)
                                if p_text:
                                    plate_votes.setdefault(vid, []).append(p_text)
                                    logger.update_plate_for_log(vid, p_text)
                            except Exception as ex:
                                print(f"[OCR ERROR] {ex}")
                            finally:
                                ocr_pending_ids.discard(vid)

                        ocr_executor.submit(async_ocr_worker, matched_id, roi_copy)

            # Determine best plate string via majority voting across frames
            display_plate = "READING..."
            if matched_id and matched_id in plate_votes and plate_votes[matched_id]:
                counts = Counter(plate_votes[matched_id])
                display_plate = counts.most_common(1)[0][0]

            # Visual box formatting
            is_unregistered = whitelist and display_plate != "READING..." and display_plate not in whitelist
            box_color = (0, 0, 255) if is_unregistered else (0, 255, 0)

            label_name = d.get('label', 'Bus').upper()
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.putText(frame, f"{label_name} ({d['confidence']})", (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, box_color, 2)

            if display_plate != "READING...":
                # Draw plate badge box
                plate_badge_text = f"PLATE: {display_plate}"
                (tw, th), _ = cv2.getTextSize(plate_badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                cv2.rectangle(frame, (x1, y2 + 5), (x1 + tw + 10, y2 + th + 15), (0, 0, 0), -1)
                cv2.putText(frame, plate_badge_text, (x1 + 5, y2 + th + 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        # Handle vehicle line crossing / presence events
        for veh_id, info in tracking_results.items():
            cx, cy = info["centroid"]
            direction = info["direction"]

            # Multi-frame voted plate number
            if veh_id in plate_votes and plate_votes[veh_id]:
                plate_no = Counter(plate_votes[veh_id]).most_common(1)[0][0]
            else:
                plate_no = "UNKNOWN"

            cv2.circle(frame, (cx, cy), 6, (255, 0, 0), -1)
            cv2.putText(frame, f"ID #{veh_id}", (cx + 10, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

            if direction and not info["is_logged"]:
                # Save JPEG snapshot evidence frame
                snap_filename = f"snap_bus_{veh_id}_{int(time.time())}.jpg"
                snap_filepath = os.path.join(SNAPSHOT_FOLDER, snap_filename)
                cv2.imwrite(snap_filepath, frame)

                # Log event to SQLite database
                logger.log_vehicle(veh_id, plate_no, direction, snapshot=snap_filename)
                trk.logged_vehicles.add(veh_id)

                # Persistent visual banner for 60 frames (~2s)
                banner_text = f"LOGGED {direction.upper()}: {plate_no} [EVIDENCE SAVED]"
                banner_timer = 60

        # Draw active event notification banner if timer active
        if banner_timer > 0:
            banner_timer -= 1
            overlay = frame.copy()
            cv2.rectangle(overlay, (15, 12), (frame_w - 15, 58), (15, 23, 42), -1)
            cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
            cv2.rectangle(frame, (15, 12), (frame_w - 15, 58), (16, 185, 129), 2)
            cv2.putText(frame, banner_text, (28, 42),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 2)

        success, buffer = cv2.imencode('.jpg', frame)
        if not success:
            continue

        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.03)

    if cap:
        cap.release()


def is_logged_in():
    """Check user authentication session."""
    return 'user' in session


# --- Flask Application Routes ---

@app.route('/')
def index():
    if is_logged_in():
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == 'admin' and password == 'admin123':
            session['user'] = username
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid credentials. Username: admin / Password: admin123"

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        return redirect(url_for('login'))

    stats = logger.get_summary_stats()
    logs = logger.get_records_list()
    cfg = load_config()
    
    # List available CCTV videos in footage/ folder
    footage_files = []
    footage_dir = os.path.join(BASE_DIR, "footage")
    if os.path.isdir(footage_dir):
        footage_files = [f for f in sorted(os.listdir(footage_dir)) if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm'))]

    return render_template(
        'dashboard.html',
        stats=stats,
        logs=logs,
        current_source=current_video_source,
        footage_files=footage_files,
        camera_name=cfg.get("camera_name", "Gate Camera 01")
    )


@app.route('/records')
def records():
    if not is_logged_in():
        return redirect(url_for('login'))

    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', 'ALL')
    records_data = logger.get_records_list(search_query=search_query, status_filter=status_filter)
    return render_template('records.html', records=records_data)


@app.route('/video_feed')
def video_feed():
    """Streaming route serving MJPEG video feed with reverse proxy support."""
    resp = Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, pre-check=0, post-check=0, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp


@app.route('/api/stats')
def api_stats():
    """Return system KPI stats for dashboard dynamic polling."""
    stats = logger.get_summary_stats()
    return jsonify(stats)


@app.route('/api/export')
def export_excel():
    """Download activity logs as a styled Excel document."""
    excel_path = logger.export_to_excel(excel_export_path)
    return send_file(
        excel_path,
        as_attachment=True,
        download_name="jkkm_bus_gate_report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route('/api/set_source', methods=['POST'])
def set_source():
    """Switch active video feed source (footage file, upload, RTSP stream, or webcam)."""
    global current_video_source, tracker
    data = request.get_json() or {}
    new_source = data.get('source', 'default_footage')

    # If specifying a footage file relative path
    if new_source.startswith("footage/"):
        new_source = os.path.join(BASE_DIR, new_source)

    current_video_source = new_source
    if tracker is not None:
        tracker.reset()

    return jsonify({"success": True, "source": current_video_source})


@app.route('/api/upload_video', methods=['POST'])
def upload_video():
    """Upload custom CCTV bus footage."""
    global current_video_source, tracker
    if 'video' not in request.files:
        return jsonify({"success": False, "error": "No video file provided"}), 400

    file = request.files['video']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    if file and is_allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)

        # Validate that OpenCV can open and decode frames from the video
        cap_test = cv2.VideoCapture(save_path)
        is_opened = cap_test.isOpened()
        ret, test_frame = cap_test.read() if is_opened else (False, None)
        cap_test.release()

        if not is_opened or not ret or test_frame is None:
            try:
                os.remove(save_path)
            except OSError:
                pass
            return jsonify({
                "success": False,
                "error": f"The video file '{filename}' could not be decoded. Please upload a standard H.264/MP4, AVI, or MOV video with readable frames."
            }), 400

        current_video_source = save_path
        if tracker is not None:
            tracker.reset()

        return jsonify({
            "success": True,
            "filename": filename,
            "path": save_path,
            "message": f"Successfully loaded video: {filename}"
        })
    else:
        return jsonify({"success": False, "error": "Unsupported video file format"}), 400


@app.route('/api/recent_logs')
def api_recent_logs():
    """Return latest 10 gate logs for dynamic real-time dashboard activity feed."""
    logs = logger.get_records_list()
    return jsonify({
        "success": True,
        "logs": logs[:10]
    })


@app.route('/api/capture_now', methods=['POST'])
def api_capture_now():
    """Manually capture and record the vehicle currently visible in the active camera stream."""
    global latest_frame_cache, detector, ocr_reader, tracker
    if latest_frame_cache is None:
        return jsonify({"success": False, "error": "No active video stream frame available."}), 400

    det, ocr, trk = get_pipeline()
    frame = latest_frame_cache.copy()
    detections = det.detect(frame) if det is not None else []

    if not detections:
        return jsonify({
            "success": False,
            "error": "No bus or vehicle detected in current camera view. Ensure a vehicle is clearly visible."
        }), 400

    # Pick the most prominent vehicle detection
    best_det = max(detections, key=lambda d: (d['box'][2]-d['box'][0]) * (d['box'][3]-d['box'][1]))
    box = best_det['box']
    label = best_det.get('label', 'Bus')
    roi = det.crop_plate_region(frame, box, lower_fraction=0.6)

    plate_no = "UNKNOWN"
    if ocr is not None and roi is not None and roi.size > 0:
        plate_str, conf = ocr.read_plate(roi)
        if plate_str:
            plate_no = plate_str

    # Annotate frame snapshot
    x1, y1, x2, y2 = box
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(frame, f"{label.upper()}: {plate_no}", (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

    now_ts = int(time.time())
    snap_filename = f"snap_manual_{now_ts}.jpg"
    snap_filepath = os.path.join(SNAPSHOT_FOLDER, snap_filename)
    cv2.imwrite(snap_filepath, frame)

    veh_id = now_ts % 1000
    logged_info = logger.log_vehicle(veh_id, plate_no, "Entry", snapshot=snap_filename)

    return jsonify({
        "success": True,
        "message": f"Successfully captured & recorded {plate_no} ({label.upper()})",
        "record": logged_info,
        "snapshot": snap_filename
    })


@app.route('/api/process_client_frame', methods=['POST'])
def api_process_client_frame():
    """
    Process live camera frames captured directly on client devices (laptops, mobile phones).
    Runs YOLOv8 vehicle detection, license plate OCR, tracking, and logs gate entries/exits.
    """
    global latest_frame_cache, tracker
    data = request.get_json() or {}
    image_b64 = data.get('image', '')

    if not image_b64:
        return jsonify({"success": False, "error": "No image data provided"}), 400

    try:
        # Strip data URL prefix if present
        if ',' in image_b64:
            image_b64 = image_b64.split(',', 1)[1]
        img_bytes = base64.b64decode(image_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            return jsonify({"success": False, "error": "Failed to decode frame"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Image decode error: {e}"}), 400

    latest_frame_cache = frame.copy()
    det, ocr, trk = get_pipeline()
    cfg = load_config()
    wlist_data = load_whitelist()
    whitelist = set(wlist_data.get("whitelist", []))

    frame_h, frame_w = frame.shape[:2]
    gate_y = int(frame_h * cfg.get("gate_line_y_fraction", 0.5))
    if trk is not None:
        trk.gate_line_y = gate_y

    detections = det.detect(frame) if det is not None else []
    tracking_results = trk.update(detections) if trk is not None else {}

    output_detections = []
    logged_event = None

    for d in detections:
        box = d['box']
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

        # Plate recognition on bumper ROI
        plate_str = "READING..."
        if matched_id is not None and ocr is not None and det is not None:
            roi = det.crop_plate_region(frame, box, lower_fraction=0.6)
            if roi is not None and roi.size > 0:
                p_text, conf = ocr.read_plate(roi)
                if p_text:
                    plate_str = p_text
                    logger.update_plate_for_log(matched_id, p_text)

        output_detections.append({
            "box": [int(x1), int(y1), int(x2), int(y2)],
            "confidence": d["confidence"],
            "label": d.get("label", "Bus").upper(),
            "plate": plate_str,
            "vehicle_id": matched_id
        })

    # Check for line-crossing or presence logging
    for veh_id, info in tracking_results.items():
        direction = info.get("direction")
        if direction and not info.get("is_logged", False):
            # Find best plate from current detections
            plate_cand = "UNKNOWN"
            for out_d in output_detections:
                if out_d.get("vehicle_id") == veh_id and out_d.get("plate") != "READING...":
                    plate_cand = out_d["plate"]
                    break

            # Save evidence snapshot
            now_ts = int(time.time())
            snap_filename = f"snap_client_{veh_id}_{now_ts}.jpg"
            snap_filepath = os.path.join(SNAPSHOT_FOLDER, snap_filename)

            # Draw visual evidence box on saved snapshot
            evidence_frame = frame.copy()
            cv2.line(evidence_frame, (0, gate_y), (frame_w, gate_y), (0, 0, 255), 2)
            for out_d in output_detections:
                bx1, by1, bx2, by2 = out_d["box"]
                cv2.rectangle(evidence_frame, (bx1, by1), (bx2, by2), (0, 255, 0), 2)
                cv2.putText(evidence_frame, f"{out_d['label']}: {out_d['plate']}", (bx1, by1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            cv2.imwrite(snap_filepath, evidence_frame)
            logger.log_vehicle(veh_id, plate_cand, direction, snapshot=snap_filename)
            trk.logged_vehicles.add(veh_id)

            logged_event = {
                "vehicle_id": veh_id,
                "plate": plate_cand,
                "direction": direction,
                "snapshot": snap_filename
            }

    return jsonify({
        "success": True,
        "detections": output_detections,
        "gate_y": gate_y,
        "frame_width": frame_w,
        "frame_height": frame_h,
        "logged_event": logged_event
    })


@app.route('/api/seed_samples', methods=['POST'])
def api_seed_samples():
    """Populate or refresh sample entry and exit records."""
    logger.seed_sample_records(force=True)
    return jsonify({"success": True, "message": "Sample entry and exit records populated successfully."})


@app.route('/static/snapshots/<filename>')
def serve_snapshot(filename):
    """Serve gate snapshot JPEG image files."""
    return send_from_directory(SNAPSHOT_FOLDER, filename)


@app.route('/manifest.json')
def serve_manifest():
    """Serve PWA web application manifest."""
    return send_from_directory(os.path.join(BASE_DIR, 'static'), 'manifest.json', mimetype='application/manifest+json')


@app.route('/sw.js')
def serve_sw():
    """Serve PWA Service Worker script with root scope."""
    response = send_from_directory(os.path.join(BASE_DIR, 'static'), 'sw.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    return response


if __name__ == '__main__':
    print("=================================================================")
    print(" JKKM BUS GATE ENTRY & EXIT MONITORING SYSTEM")
    print(" Running at: http://127.0.0.1:5000")
    print(" Default Login: admin / admin123")
    print("=================================================================")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
