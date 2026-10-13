"""
train_yolo.py
-------------
CCTV Dataset Extraction & YOLOv8 Model Training Pipeline.
Use this script to:
  1. Extract frames from CCTV videos in footage/
  2. Organize dataset for YOLO training
  3. Train or fine-tune YOLOv8 on your campus bus/vehicle data
"""

import os
import sys
import argparse
import cv2
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOOTAGE_DIR = os.path.join(BASE_DIR, "footage")
DATASET_DIR = os.path.join(BASE_DIR, "dataset")


def extract_frames(video_path: str, output_dir: str, frame_interval: int = 15):
    """
    Extract frames from a CCTV video at regular intervals for dataset annotation.
    
    :param video_path: Path to source video file
    :param output_dir: Destination directory for extracted image frames
    :param frame_interval: Extract 1 frame every N frames
    """
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Could not open video: {video_path}")
        return 0

    count = 0
    saved = 0
    base_name = os.path.splitext(os.path.basename(video_path))[0]

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if count % frame_interval == 0:
            frame_filename = f"{base_name}_frame_{count:05d}.jpg"
            save_path = os.path.join(output_dir, frame_filename)
            cv2.imwrite(save_path, frame)
            saved += 1
        count += 1

    cap.release()
    print(f"[EXTRACT] Saved {saved} frames from {os.path.basename(video_path)} into {output_dir}")
    return saved


def extract_all_footage(frame_interval: int = 20):
    """Extract frames from all video files found in the footage/ directory."""
    raw_images_dir = os.path.join(DATASET_DIR, "raw_images")
    os.makedirs(raw_images_dir, exist_ok=True)

    video_exts = ('.mp4', '.avi', '.mov', '.mkv', '.webm')
    videos = [
        os.path.join(FOOTAGE_DIR, f)
        for f in os.listdir(FOOTAGE_DIR)
        if f.lower().endswith(video_exts)
    ]

    if not videos:
        print("[WARNING] No video files found in footage/ directory.")
        print("Please copy your CCTV video files (.mp4, .avi) into the footage/ folder.")
        return 0

    total_saved = 0
    for v in videos:
        total_saved += extract_frames(v, raw_images_dir, frame_interval)

    print(f"\n[DONE] Total {total_saved} frames extracted to: {raw_images_dir}")
    print("[NEXT STEP] Annotate images with tools like LabelImg, Roboflow, or CVAT,")
    print("then place images and YOLO format txt labels in dataset/images and dataset/labels.")
    return total_saved


def train_yolo(data_yaml="data.yaml", epochs=50, imgsz=640, batch=8, model="yolov8n.pt"):
    """
    Train YOLOv8 on custom annotated bus dataset.
    
    :param data_yaml: Path to YOLO dataset YAML configuration file
    :param epochs: Number of training epochs
    :param imgsz: Image resolution (default 640)
    :param batch: Batch size
    :param model: Base pretrained weights (yolov8n.pt)
    """
    if not os.path.exists(data_yaml):
        # Generate a starter data.yaml template if not already present
        starter_yaml = f"""# YOLOv8 Dataset Configuration
path: {DATASET_DIR}
train: images/train
val: images/val

# Classes
names:
  0: bus
  1: license_plate
"""
        with open(data_yaml, "w") as f:
            f.write(starter_yaml)
        print(f"[CREATED] Starter dataset config: {data_yaml}")

    print(f"[INFO] Starting YOLOv8 fine-tuning with base model {model}...")
    yolo_model = YOLO(model)
    results = yolo_model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project="runs/detect",
        name="bus_gate_custom",
        plots=True
    )
    print("\n[SUCCESS] Training completed! Best model saved in runs/detect/bus_gate_custom/weights/best.pt")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bus Monitoring CCTV Dataset & Training Helper")
    parser.add_argument("--extract", action="store_true", help="Extract frames from footage/ videos")
    parser.add_argument("--train", action="store_true", help="Start YOLOv8 model training")
    parser.add_argument("--epochs", type=int, default=30, help="Training epochs")
    parser.add_argument("--interval", type=int, default=15, help="Frame extraction interval")

    args = parser.parse_args()

    if args.extract:
        extract_all_footage(frame_interval=args.interval)
    elif args.train:
        train_yolo(epochs=args.epochs)
    else:
        print("Usage:")
        print("  py -3.11 train_yolo.py --extract        # Extract dataset frames from CCTV videos in footage/")
        print("  py -3.11 train_yolo.py --train          # Train YOLOv8 on annotated dataset")
