import base64
from pathlib import Path
import os
import re
import torch
import cv2
import numpy as np
import pytesseract
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = PROJECT_ROOT / "models" / "yolov8n.engine"

TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

TRIGGER_WORDS = ["password", "api", "secret", "confidential", "private", ".env", "key"]

INFERENCE_WIDTH = 1280


def _contains_trigger_words(text: str) -> bool:
    lower_text = text.lower()
    return any(word in lower_text for word in TRIGGER_WORDS)


try:
    # FORCED NATIVE WINDOWS GPU FALLBACK
    print("[frame-worker] Loading standard PyTorch model for native Windows...")
    model = YOLO("yolov8n.pt")

    # FORCE YOLO ONTO THE GPU
    model.to("cuda")

    # This will explicitly prove it is using your RTX 4050!
    print(f"[frame-worker] Model loaded successfully on device: {model.device}")
except Exception as exc:
    model = None
    print(f"[frame-worker] FATAL: failed to load YOLO model: {exc}")


def _decode_base64_image(image_base64: str) -> np.ndarray | None:
    """Decode base64 payload into an OpenCV BGR image."""
    try:
        raw_bytes = base64.b64decode(image_base64, validate=True)
        img_array = np.frombuffer(raw_bytes, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return image
    except Exception:
        return None


def _extract_detected_classes(result: object) -> list[str]:
    """Extract unique class names from a single Ultralytics result object."""
    boxes = getattr(result, "boxes", None)
    if boxes is None or getattr(boxes, "cls", None) is None:
        return []

    cls_values = boxes.cls.tolist()
    names_map = getattr(result, "names", {}) or {}

    detected: list[str] = []
    for cls_value in cls_values:
        cls_idx = int(cls_value)
        class_name = names_map.get(cls_idx, str(cls_idx))
        if class_name not in detected:
            detected.append(class_name)
    return detected


def _sanitize_ocr_text(text: str) -> str:
    """
    Production-grade redaction using advanced Regex.
    Catches variations of passwords, AWS keys, and generic secrets.
    """
    if not text:
        return ""

    redacted = text

    # 1. AWS Access Keys (Standard Format: AKIA followed by 16 alphanumeric characters)
    redacted = re.sub(r'(?i)\b(AKIA[0-9A-Z]{16})\b', r'<REDACTED_AWS_ACCESS_KEY>', redacted)

    # 2. Generic Secret Keys (Catches "AWS Secret Key: xyz" or "Secret: xyz")
    redacted = re.sub(r'(?i)((?:secret|access)[ _]?(?:key|token)?\s*(?:is|:|=|-)\s*)\S+', r'\1<REDACTED_SECRET>', redacted)

    # 3. Passwords (Catches "password is xyz", "Pass: xyz", "Password=xyz")
    redacted = re.sub(r'(?i)(pass(?:word)?\s*(?:is|:|=|-)\s*)\S+', r'\1<REDACTED_PASSWORD>', redacted)

    # Clean up excessive OCR noise/newlines so it doesn't spam the UI
    redacted = re.sub(r'\n+', ' | ', redacted).strip()

    return redacted


def _run_ocr_sync(image: np.ndarray) -> str:
    """Synchronous OCR task to be run in a separate thread."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return pytesseract.image_to_string(gray).strip()