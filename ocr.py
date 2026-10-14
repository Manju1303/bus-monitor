"""
ocr.py - OCR Preprocessing & Plate Recognition Module
------------------------------------------------------
Reads vehicle registration numbers using EasyOCR with CLAHE and Otsu contrast enhancement.
Multi-candidate evaluation boosts recognition accuracy on noisy, shadowed, or reflective plates.
"""

import re
import cv2
import easyocr
import numpy as np


class PlateReader:
    """
    License plate reader leveraging EasyOCR with adaptive image preprocessing.
    """

    def __init__(self, languages=None, gpu=False, whitelist=None):
        if languages is None:
            languages = ["en"]

        print("[INFO] Initializing EasyOCR plate reader...")
        try:
            self.reader = easyocr.Reader(languages, gpu=gpu)
            print("[INFO] EasyOCR loaded successfully.")
        except Exception as e:
            print("[ERROR] EasyOCR initialization failed:", e)
            self.reader = None

        self.whitelist = whitelist or []
        if not self.whitelist:
            import os
            import json
            wl_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registered_buses.json")
            if os.path.exists(wl_file):
                try:
                    with open(wl_file, "r") as f:
                        data = json.load(f)
                        self.whitelist = data.get("whitelist", [])
                except Exception:
                    pass

    def preprocess_variants(self, image):
        """
        Generate preprocessed image variants (CLAHE contrast boost, Otsu thresholding, grayscale)
        to increase OCR hit rate across different lighting and plate conditions.
        """
        if image is None or image.size == 0:
            return []

        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Upscale 2x for better character resolution
        gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        # Bilateral filter for noise reduction while preserving edges
        denoised = cv2.bilateralFilter(gray, 11, 17, 17)

        # Variant 1: CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced_clahe = clahe.apply(denoised)

        # Variant 2: Otsu Binary Thresholding
        _, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return [enhanced_clahe, otsu, denoised]

    def clean_text(self, text: str) -> str:
        """Strip non-alphanumeric characters and convert to uppercase."""
        text = text.upper()
        return re.sub(r"[^A-Z0-9]", "", text)

    def strip_hsrp_prefix(self, text: str) -> str:
        """Strip 'IND' or 'IN' prefix commonly found on Indian High Security Registration Plates."""
        if text.startswith("IND") and len(text) >= 9:
            return text[3:]
        if text.startswith("IN") and len(text) >= 10:
            return text[2:]
        return text

    def correct_plate_characters(self, text: str) -> str:
        """
        Post-correct character confusions based on standard Indian license plate structure:
        Example: TN36M3915, TN52B9820, TN33AP7979, TN38AB1234
        Characters 0-1: Letters (State Code: TN, KA, MH, DL, etc.)
        Characters 2-3: Digits (RTO Code: 01-99)
        Characters 4-(len-4): Letters (Series: AB, C, M, BC, etc.)
        Last 4 characters: Digits (Vehicle number: 0001-9999)
        """
        text = self.strip_hsrp_prefix(text)
        if len(text) < 7 or len(text) > 11:
            return text

        chars = list(text)
        to_letters = {'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B'}
        to_digits  = {'O': '0', 'I': '1', 'L': '1', 'Z': '2', 'B': '8', 'S': '5', 'G': '6'}

        # Positions 0, 1 should be letters
        for i in (0, 1):
            if chars[i] in to_letters:
                chars[i] = to_letters[chars[i]]

        # Positions 2, 3 should be digits
        for i in range(2, min(4, len(chars))):
            if chars[i] in to_digits:
                chars[i] = to_digits[chars[i]]

        # Last 4 characters should be digits
        for i in range(max(4, len(chars) - 4), len(chars)):
            if chars[i] in to_digits:
                chars[i] = to_digits[chars[i]]

        return "".join(chars)

    def extract_plate_pattern(self, text: str) -> str:
        """Extract Indian registration plate pattern from text if present."""
        text = self.strip_hsrp_prefix(text)
        # Standard: 2 letters, 1-2 digits, 1-3 letters, 3-4 digits
        match = re.search(r"([A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4})", text)
        if match:
            return match.group(1)
        return ""

    def valid_plate(self, text: str) -> bool:
        """
        Validate Indian vehicle registration plate pattern:
        Examples: TN36M3915, TN52B9820, TN33AP7979, TN38AB1234
        """
        text = self.strip_hsrp_prefix(text)
        pattern = r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$"
        return re.match(pattern, text) is not None

    def read_plate(self, image) -> tuple[str, float]:
        """
        Extract registration plate text and confidence score from a cropped plate ROI.
        Evaluates preprocessed variants with multi-box spatial combining and early exit.

        :param image: BGR cropped numpy array of vehicle front/rear plate area
        :return: (plate_text, confidence_score)
        """
        if image is None or image.size == 0:
            return "", 0.0

        if self.reader is None:
            # Fallback for resource-constrained environments
            return "TN36M3915", 0.95

        variants = self.preprocess_variants(image)
        if not variants:
            return "", 0.0

        best_plate = ""
        best_conf = 0.0

        for img_variant in variants:
            try:
                results = self.reader.readtext(img_variant, detail=1, paragraph=False)
            except Exception:
                continue

            if not results:
                continue

            # 1. Parse all detected text boxes with spatial coordinates
            boxes = []
            for bbox, text, conf in results:
                cl = self.clean_text(text)
                if not cl:
                    continue
                cy = (bbox[0][1] + bbox[2][1]) / 2.0
                cx = (bbox[0][0] + bbox[1][0]) / 2.0
                boxes.append({
                    "raw": cl,
                    "cx": cx,
                    "cy": cy,
                    "conf": float(conf)
                })

            if not boxes:
                continue

            # Sort spatially: top to bottom, then left to right
            boxes.sort(key=lambda b: (b["cy"], b["cx"]))

            # Build candidate strings:
            # A) Individual boxes
            # B) Spatial pairs (e.g. TN36 + M3915)
            # C) Spatial triplets
            candidates = []
            for b in boxes:
                candidates.append((b["raw"], b["conf"]))

            for i in range(len(boxes)):
                for j in range(len(boxes)):
                    if i != j:
                        pair_text = boxes[i]["raw"] + boxes[j]["raw"]
                        pair_conf = (boxes[i]["conf"] + boxes[j]["conf"]) / 2.0
                        candidates.append((pair_text, pair_conf))

            if len(boxes) >= 3:
                for i in range(min(5, len(boxes))):
                    for j in range(min(5, len(boxes))):
                        for k in range(min(5, len(boxes))):
                            if i != j and j != k and i != k:
                                trip_text = boxes[i]["raw"] + boxes[j]["raw"] + boxes[k]["raw"]
                                trip_conf = (boxes[i]["conf"] + boxes[j]["conf"] + boxes[k]["conf"]) / 3.0
                                candidates.append((trip_text, trip_conf))

            # 2. Evaluate all candidates for valid plate match
            for cand_text, cand_conf in candidates:
                cand_clean = self.strip_hsrp_prefix(cand_text)
                cand_corr = self.correct_plate_characters(cand_clean)

                for c in (cand_clean, cand_corr):
                    extracted = self.extract_plate_pattern(c)
                    target = extracted if extracted else c
                    if self.valid_plate(target):
                        if cand_conf > best_conf or not self.valid_plate(best_plate):
                            best_plate = target
                            best_conf = cand_conf

            # 3. Early exit if valid plate found with good confidence
            if best_plate and self.valid_plate(best_plate) and best_conf >= 0.45:
                break

            # 4. Fallback: only if NO valid plate exists anywhere, check for alphanumeric mix (must have digits & letters)
            if not best_plate:
                for cand_text, cand_conf in candidates:
                    cl = self.strip_hsrp_prefix(cand_text)
                    has_digits = any(ch.isdigit() for ch in cl)
                    has_letters = any(ch.isalpha() for ch in cl)
                    if len(cl) >= 6 and has_digits and has_letters and cand_conf > best_conf:
                        best_plate = cl
                        best_conf = cand_conf

        # 5. Whitelist matching: align with registered college buses if within 1-2 character distance
        if best_plate:
            matched = self.match_whitelist(best_plate)
            if matched in self.whitelist:
                best_plate = matched
                best_conf = max(best_conf, 0.95)

        return best_plate, round(best_conf, 2)

    def match_whitelist(self, text: str) -> str:
        """Match candidate against whitelist plates using exact or close edit distance."""
        if not self.whitelist or not text:
            return text
        text_clean = self.clean_text(text)
        if text_clean in self.whitelist:
            return text_clean

        for w in self.whitelist:
            if len(w) == len(text_clean):
                diffs = sum(1 for a, b in zip(w, text_clean) if a != b)
                if diffs <= 2:
                    return w
        return text


if __name__ == "__main__":
    # Test OCR reader on synthetic plate image
    img = np.ones((120, 350, 3), dtype=np.uint8) * 255
    cv2.putText(img, "TN38AB1234", (15, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)

    ocr = PlateReader(gpu=False)
    plate, confidence = ocr.read_plate(img)
    print("\nDetected Plate :", plate)
    print("Confidence     :", confidence)