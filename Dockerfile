# Python 3.11 base image
FROM python:3.11-slim

# Prevent Python from writing .pyc files & enable unbuffered stdout logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies required for OpenCV and GL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Pre-cache AI weights (YOLOv8 & EasyOCR) to avoid download timeouts during runtime
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt'); import easyocr; easyocr.Reader(['en'], gpu=False)"

# Expose default application port
EXPOSE 5000

ENV PORT=5000

# Launch production server with multi-threading
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 8 --timeout 120 app:app"]
