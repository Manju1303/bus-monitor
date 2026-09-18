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

    def __init__(self, languages=None, gpu=False):
        if languages is None:
            languages = ["en"]

        print("[INFO] Initializing EasyOCR plate reader...")
        try:
            self.reader = easyocr.Reader(languages, gpu=gpu)
            print("[INFO] EasyOCR loaded successfully.")
        except Exception as e:
            print("[ERROR] EasyOCR initialization failed:", e)
            self.reader = None

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

    def valid_plate(self, text: str) -> bool:
        """
        Validate Indian vehicle registration plate pattern:
        Examples: TN38AB1234, KA01MN5678, DL3CC1234, MH12DE9999
        """
        pattern = r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$"
        return re.match(pattern, text) is not None

    def read_plate(self, image) -> tuple[str, float]:
        """
        Extract registration plate text and confidence score from a cropped plate ROI.
        Evaluates multiple image preprocessing variants to maximize OCR accuracy.

        :param image: BGR cropped numpy array of vehicle front/rear plate area
        :return: (plate_text, confidence_score)
        """
        if self.reader is None or image is None or image.size == 0:
            return "", 0.0

        variants = self.preprocess_variants(image)
        if not variants:
            return "", 0.0

        best_plate = ""
        best_conf = 0.0

        for img_variant in variants:
            try:
                results = self.reader.readtext(img_variant, detail=1, paragraph=False)
            except Exception as e:
                continue

            for _, text, conf in results:
                plate = self.clean_text(text)
                conf_val = float(conf)

                if self.valid_plate(plate):
                    if conf_val > best_conf:
                        best_plate = plate
                        best_conf = conf_val
                elif best_plate == "" and len(plate) >= 5 and conf_val > best_conf:
                    # Fallback candidate if standard pattern match hasn't succeeded yet
                    best_plate = plate
                    best_conf = conf_val

        return best_plate, round(best_conf, 2)


if __name__ == "__main__":
    # Test OCR reader on synthetic plate image
    img = np.ones((120, 350, 3), dtype=np.uint8) * 255
    cv2.putText(img, "TN38AB1234", (15, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)

    ocr = PlateReader(gpu=False)
    plate, confidence = ocr.read_plate(img)
    print("\nDetected Plate :", plate)
    print("Confidence     :", confidence)