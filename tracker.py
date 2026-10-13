"""
tracker.py - Spatial Vehicle Tracker for Bus Monitoring System
--------------------------------------------------------------
This module tracks vehicle centroids across video frames using Euclidean distance matching.
It assigns persistent unique vehicle IDs, determines movement direction (Entry vs Exit)
across a virtual gate line, and prevents duplicate logs.
"""

import numpy as np


class VehicleTracker:
    """
    Euclidean Centroid Tracker that assigns a unique persistent ID to each moving vehicle
    and detects crossing over virtual campus gate line thresholds.
    """
    
    def __init__(self, max_disappeared: int = 15, max_distance: int = 80, gate_line_y: int = 250):
        """
        :param max_disappeared: Frames to wait before unregistering a lost object ID
        :param max_distance: Max pixel displacement between frames to consider the same object
        :param gate_line_y: Horizontal Y-coordinate line representing the Campus Gate
        """
        self.next_object_id = 1
        self.objects = {}         # object_id -> centroid (x, y)
        self.disappeared = {}     # object_id -> count of lost frames
        self.positions = {}       # object_id -> list of previous Y centroids [(y_old, y_new)]
        self.logged_vehicles = set() # Set of object IDs that have already been recorded
        
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance
        self.gate_line_y = gate_line_y

    def reset(self):
        """Reset tracking state for new video stream."""
        self.next_object_id = 1
        self.objects.clear()
        self.disappeared.clear()
        self.positions.clear()
        self.logged_vehicles.clear()

    def register(self, centroid: tuple):
        """Register a new detected vehicle with a unique ID."""
        self.objects[self.next_object_id] = centroid
        self.disappeared[self.next_object_id] = 0
        self.positions[self.next_object_id] = [centroid[1]]
        self.next_object_id += 1

    def deregister(self, object_id: int):
        """Remove a vehicle ID when it exits the camera view."""
        if object_id in self.objects:
            del self.objects[object_id]
            del self.disappeared[object_id]
            del self.positions[object_id]

    def update(self, detections: list):
        """
        Update tracker with current frame bounding boxes.
        
        :param detections: List of detection dicts with key 'box': (x1, y1, x2, y2)
        :return: Dict of active {object_id: (centroid_x, centroid_y, box, direction_event)}
        """
        if len(detections) == 0:
            # Mark all existing objects as disappeared for this frame
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return {}

        # Calculate centroids for current frame detections
        input_centroids = []
        input_boxes = []
        for det in detections:
            x1, y1, x2, y2 = det['box']
            cX = int((x1 + x2) / 2.0)
            cY = int((y1 + y2) / 2.0)
            input_centroids.append((cX, cY))
            input_boxes.append((x1, y1, x2, y2))

        # If no objects are currently tracked, register all input centroids
        if len(self.objects) == 0:
            for c in input_centroids:
                self.register(c)
        else:
            object_ids = list(self.objects.keys())
            object_centroids = list(self.objects.values())

            # Compute Euclidean distance matrix between existing objects and new centroids
            D = np.linalg.norm(np.array(object_centroids)[:, np.newaxis] - np.array(input_centroids), axis=2)

            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]

            used_rows = set()
            used_cols = set()

            for (row, col) in zip(rows, cols):
                if row in used_rows or col in used_cols:
                    continue

                if D[row, col] > self.max_distance:
                    continue

                object_id = object_ids[row]
                new_centroid = input_centroids[col]

                self.objects[object_id] = new_centroid
                self.disappeared[object_id] = 0
                self.positions[object_id].append(new_centroid[1])
                
                used_rows.add(row)
                used_cols.add(col)

            # Unused rows -> lost objects
            unused_rows = set(range(0, D.shape[0])).difference(used_rows)
            for row in unused_rows:
                object_id = object_ids[row]
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)

            # Unused cols -> new vehicles entering view
            unused_cols = set(range(0, D.shape[1])).difference(used_cols)
            for col in unused_cols:
                self.register(input_centroids[col])

        # Evaluate gate line crossing events (Entry vs Exit)
        tracking_results = {}
        for object_id, centroid in self.objects.items():
            direction = None
            pos_history = self.positions[object_id]
            
            if len(pos_history) >= 2:
                prev_y = pos_history[-2]
                curr_y = pos_history[-1]
                
                # Top-to-Bottom crossing -> Entry
                if prev_y < self.gate_line_y and curr_y >= self.gate_line_y:
                    direction = "Entry"
                # Bottom-to-Top crossing -> Exit
                elif prev_y > self.gate_line_y and curr_y <= self.gate_line_y:
                    direction = "Exit"

            tracking_results[object_id] = {
                "centroid": centroid,
                "direction": direction,
                "is_logged": object_id in self.logged_vehicles
            }

        return tracking_results


# --- Simple Module Test ---
if __name__ == "__main__":
    print("[TEST] Initializing VehicleTracker test...")
    tracker = VehicleTracker(gate_line_y=200)
    
    # Frame 1: Bus at Y=150 (Above Gate Line)
    res1 = tracker.update([{"box": (100, 100, 200, 200)}])
    print(f"Frame 1 Tracked Objects: {res1}")
    
    # Frame 2: Bus moves down to Y=220 (Crosses Gate Line Y=200 downwards)
    res2 = tracker.update([{"box": (105, 170, 205, 270)}])
    print(f"Frame 2 Tracked Objects: {res2}")
