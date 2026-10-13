# JKKM Bus Gate Entry & Exit Monitoring System

An AI-powered computer vision security system designed for JKK Munirajah College for automated detection, tracking, license plate identification, entry/exit timestamp logging, JPEG evidence capturing, and Excel reporting of buses at campus gate checkpoints.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)
![YOLOv8](https://img.shields.io/badge/YOLOv8-Vehicle%20Detection-green.svg)
![EasyOCR](https://img.shields.io/badge/EasyOCR-License%20Plate-orange.svg)
![SQLite](https://img.shields.io/badge/SQLite-Database-lightgrey.svg)
![Flask](https://img.shields.io/badge/Flask-Web%20Dashboard-red.svg)

---

## 🌟 Key Features

- **🚌 Bus-Only Vehicle Filtering**: Powered by custom YOLOv8 detection scoped exclusively to bus class detection (Class ID 5), eliminating false positives from cars, bikes, or pedestrians.
- **📍 Centroid Line-Crossing Tracking**: Tracks bus movement vectors across defined gate entry thresholds to calculate exact entry times, exit times, and stay duration on campus.
- **🔤 Contrast-Enhanced License Plate OCR**: Utilizes EasyOCR with CLAHE (Contrast Limited Adaptive Histogram Equalization) and Otsu thresholding preprocessing for high-accuracy Indian registration plate extraction.
- **📊 Multi-Frame Majority Voting**: Evaluates plate OCR predictions over multiple contiguous frames for each bus to pick the highest-confidence registration string.
- **🗄️ Thread-Safe SQLite Database**: High-speed, concurrent-safe database backend ensuring zero file lock conflicts during live video processing.
- **📸 Automated JPEG Snapshot Capturing**: Captures full-resolution camera evidence snapshots whenever a bus crosses the gate boundary line.
- **📥 One-Click Excel Reporting**: Generates styled `.xlsx` reports on demand via `/api/export` with custom headers, formatting, and duration statistics.
- **🌐 Responsive Web Dashboard**: Dark-mode Flask web dashboard with live MJPEG surveillance streaming, real-time activity feeds, video upload controls, and activity log filters.
- **⚙️ Configurable Runtime Options**: Configurable `config.json` for adjusting camera names, gate threshold lines, and detection confidence thresholds without modifying source code.

---

## 📁 Repository Structure

```
Bus-gate-entry-and-exit-monitoring-system/
├── app.py                   # Flask Web Server & MJPEG video streaming API
├── main.py                  # CLI pipeline runner for video files or live streams
├── detector.py              # YOLOv8 bus-only detection module
├── tracker.py               # Centroid vector tracking & gate threshold crossing module
├── ocr.py                   # EasyOCR plate extraction with CLAHE & Otsu preprocessing
├── database.py              # Thread-safe SQLite backend with Excel export generator
├── excel.py                 # Direct Excel logger fallback
├── config.json              # System configuration parameters
├── registered_buses.json    # Campus bus whitelist & alert configuration
├── requirements.txt         # Project Python dependencies
├── train_yolo.py            # CCTV dataset frame extraction & YOLOv8 model training helper
├── create_sample_footage.py # CCTV sample video generator for testing
├── project_documentation.md # Technical documentation
├── footage/                 # Folder for CCTV video footage samples
│   ├── gate_cctv_bus_entry.mp4
│   └── campus_bus_gate_sample.mp4
├── static/
│   ├── css/
│   │   └── style.css        # Dashboard styling & dark mode UI design system
│   ├── js/
│   │   └── script.js        # Live polling & UI interactive handlers
│   └── snapshots/           # Auto-saved JPEG gate event snapshots
└── templates/
    ├── login.html           # Authentication portal
    ├── dashboard.html       # Live monitoring dashboard
    └── records.html         # Interactive activity log table with export
```

---

## 🚀 Installation & Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/Arthi117/Bus-gate-entry-and-exit-monitoring-system.git
cd Bus-gate-entry-and-exit-monitoring-system
```

### 2. Set Up Virtual Environment

```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> **Note**: Torch and OpenCV will be automatically installed. First-time execution will download the pre-trained `yolov8n.pt` model weights and EasyOCR English language model.

---

## 💻 Running the System

### Option A: Launch Web Dashboard (Recommended)

Start the Flask web server:

```bash
python app.py
```

- **URL**: `http://127.0.0.1:5000`
- **Default Operator Credentials**:
  - **Username**: `admin`
  - **Password**: `admin123`

### Option B: Run via Command Line Interface (CLI)

Run the detection pipeline directly from terminal on default CCTV footage:

```bash
python main.py
```

Run on custom CCTV video file:

```bash
python main.py footage/gate_cctv_bus_entry.mp4
```

Run on live USB webcam (Camera ID 0):

```bash
python main.py 0
```

---

## ⚙️ Configuration

System parameters can be adjusted via `config.json`:

```json
{
  "gate_line_y_fraction": 0.5,
  "camera_name": "Gate Camera 01",
  "min_confidence": 0.35
}
```

- **`gate_line_y_fraction`**: Horizontal line threshold position as a fraction of frame height (0.1 - 0.9).
- **`camera_name`**: Label printed on video feeds and logs.
- **`min_confidence`**: Minimum YOLOv8 confidence score threshold for bus detection.

---

## 📡 REST API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/video_feed` | `GET` | Multipart MJPEG camera surveillance video stream |
| `/api/stats` | `GET` | Returns JSON summary stats (total logs, on campus, exited today) |
| `/api/export` | `GET` | Downloads the generated `.xlsx` Excel activity report |
| `/api/set_source` | `POST` | Switches active surveillance video feed source |
| `/api/upload_video` | `POST` | Uploads a custom video file for processing |
| `/static/snapshots/<filename>` | `GET` | Serves JPEG snapshot image evidence |

---

## 🛠️ Technology Stack

- **Computer Vision & Object Detection**: Ultralytics YOLOv8, OpenCV
- **Optical Character Recognition**: EasyOCR, CLAHE, Otsu Thresholding
- **Spatial Tracking**: Centroid Tracking Algorithm
- **Web Backend & Streaming**: Flask, SQLite3, openpyxl
- **Frontend UI**: Vanilla HTML5, Modern Glassmorphism CSS, JavaScript (ES6)

---

## 📄 License

This project is open-source under the MIT License.
