"""
detector.py - YOLOv8 Object Detection Module for Bus Monitoring System
---------------------------------------------------------------------
This module uses Ultralytics YOLOv8 to detect vehicles (specifically buses)
in video frames or images, extract their bounding boxes, and crop regions
of interest (ROI) for license plate recognition.
"""

import cv2
import numpy as np
from ultralytics import YOLO


class BusDetector:
    """
    BusDetector wraps YOLOv8 to detect vehicles in video frames.
    
    COCO Dataset Class Indexes:
      5: Bus  ← Only buses are detected and tracked
    """

    def __init__(self, model_name: str = "yolov8n.pt", confidence: float = 0.25):
        """
        Initialize the YOLOv8 model.

        :param model_name: YOLO model file (e.g., 'yolov8n.pt' or 'models/yolov8n.pt')
        :param confidence: Minimum confidence score (0.0 to 1.0) to filter detections
        """
        import os
        model_path = model_name
        if not os.path.exists(model_path):
            models_dir_path = os.path.join("models", model_name)
            if os.path.exists(models_dir_path):
                model_path = models_dir_path

        print(f"[INFO] Loading YOLOv8 model: {model_path}...")
        self.model = YOLO(model_path)
        self.confidence = confidence

        # Only track buses (COCO class ID 5)
        self.target_classes = [5]

        
    def detect(self, frame: np.ndarray):
        """
        Perform vehicle detection on a single frame.
        
        :param frame: BGR image numpy array from OpenCV
        :return: List of detections, each formatted as:
                 {"box": (x1, y1, x2, y2), "confidence": score, "class_id": class_id, "label": label_name}
        """
        results = self.model(frame, verbose=False)[0]
        detections = []
        
        for box in results.boxes:
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            
            # Filter by confidence threshold and target vehicle class
            if conf >= self.confidence and cls_id in self.target_classes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                label = self.model.names[cls_id]
                
                detections.append({
                    "box": (x1, y1, x2, y2),
                    "confidence": round(conf, 2),
                    "class_id": cls_id,
                    "label": label
                })
                
        return detections

    def crop_plate_region(self, frame: np.ndarray, box: tuple, lower_fraction: float = 0.5):
        """
        Crop the lower portion of a vehicle bounding box, where the license plate
        is typically located, for OCR processing.
        
        :param frame: Full frame image
        :param box: Vehicle bounding box (x1, y1, x2, y2)
        :param lower_fraction: Fraction of bottom region to crop (default bottom 50%)
        :return: Cropped image numpy array
        """
        x1, y1, x2, y2 = box
        height = y2 - y1
        
        # Focus on the lower part of the detected vehicle box
        crop_y1 = int(y1 + height * (1.0 - lower_fraction))
        cropped = frame[crop_y1:y2, x1:x2]
        
        return cropped


# --- Simple Module Test ---
if __name__ == "__main__":
    print("[TEST] Initializing BusDetector test...")
    detector = BusDetector(confidence=0.3)
    
    # Create a blank dummy image to test detection pipeline setup
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    results = detector.detect(dummy_frame)
    print(f"[TEST] Detection completed successfully. Detections found in blank frame: {len(results)}")
