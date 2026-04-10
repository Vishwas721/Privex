import base64
from pathlib import Path
import os
import re
import time
import torch
import cv2
import numpy as np
import easyocr
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = PROJECT_ROOT / "models" / "yolov8n.engine"

TRIGGER_WORDS = ["password", "api", "secret", "confidential", "private", ".env", "key"]

INFERENCE_WIDTH = 1280


def _contains_trigger_words(text: str) -> bool:
    lower_text = text.lower()
    return any(word in lower_text for word in TRIGGER_WORDS)


try:
    print("[frame-worker] Loading standard PyTorch model for native Windows...")
    model = YOLO("yolov8n.pt")

    # SAFE HARDWARE ROUTING
    if torch.cuda.is_available():
        model.to("cuda")
        print(f"[frame-worker] YOLO loaded successfully on GPU: {model.device}")
    else:
        print("[frame-worker] CUDA unavailable, keeping YOLO on CPU.")

except Exception as exc:
    model = None
    print(f"[frame-worker] FATAL: failed to load YOLO model: {exc}")


try:
    # 🛑 FIX 1: Load the faster, first-generation recognition network
    use_gpu = torch.cuda.is_available()
    print(f"[frame-worker] Initializing EasyOCR reader. GPU acceleration requested: {use_gpu}")
    ocr_reader = easyocr.Reader(['en'], gpu=use_gpu, recog_network='latin_g1')
    print(f"[frame-worker] EasyOCR reader loaded successfully. GPU active: {use_gpu}")
except Exception as exc:
    ocr_reader = None
    print(f"[frame-worker] FATAL: failed to load EasyOCR reader: {exc}")


def _decode_base64_image(image_base64: str) -> np.ndarray | None:
    """Decode base64 payload into an OpenCV BGR image."""
    try:
        raw_bytes = base64.b64decode(image_base64, validate=True)
        img_array = np.frombuffer(raw_bytes, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return image
    except Exception:
        return None


def _predict_yolo_sync(image: np.ndarray):
    if model is None:
        return []
    # 🛑 NEW: Use built-in ByteTrack to assign consistent IDs to windows across frames
    results = model.track(image, persist=True, verbose=False, tracker="bytetrack.yaml")
    return results


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

    if any(word in redacted.lower() for word in TRIGGER_WORDS):
        print(f"[Regex] Trigger word matched in: {redacted}")

    return redacted


def _run_ocr_sync(image: np.ndarray) -> str:
    """Synchronous OCR task to be run in a separate thread using EasyOCR."""
    if ocr_reader is None:
        return ""
    start = time.time()
    try:
        # 🛑 FIX 2: Force Greedy Decoding and restrict the character set!
        results = ocr_reader.readtext(
            image,
            detail=0,
            decoder='greedy',
            paragraph=False,
            batch_size=16,
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_/='
        )
        text = " ".join(results).strip()
        print(f"[OCR] Extracted: {text}")
        return text
    except Exception as exc:
        print(f"[frame-worker] OCR error: {exc}")
        return ""
    finally:
        print(f"[OCR TIMING] {time.time() - start} seconds")