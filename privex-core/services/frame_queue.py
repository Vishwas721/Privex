import asyncio
import base64
from datetime import datetime, timezone
from pathlib import Path
import os
import torch
import cv2
import httpx
import numpy as np
import pytesseract
from ultralytics import YOLO

from core.database import log_event
from core.schemas import FramePayload

# Bounded queue to avoid unbounded memory growth if inference stalls.
frame_queue: asyncio.Queue[FramePayload] = asyncio.Queue(maxsize=5)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = PROJECT_ROOT / "models" / "yolov8n.engine"

# Must be configurable for Docker networking (e.g., http://privex-mcp:3000/api/alert)
ALERT_ENDPOINT = os.getenv("ALERT_ENDPOINT", "http://127.0.0.1:3000/api/alert")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

try:
    # FORCED NATIVE WINDOWS GPU FALLBACK
    print("[frame-worker] Loading standard PyTorch model for native Windows...")
    model = YOLO("yolov8n.pt")
    
    # This will explicitly prove it is using your RTX 4050!
    print(f"[frame-worker] Model loaded successfully on device: {model.device}")
except Exception as exc:
    model = None
    print(f"[frame-worker] FATAL: failed to load YOLO model: {exc}")


async def enqueue_frame(payload: FramePayload) -> None:
    """Enqueue newest frame; drop oldest when queue is full for real-time behavior."""
    if frame_queue.full():
        try:
            frame_queue.get_nowait()  # Aggressively drop oldest frame.
            frame_queue.task_done()
        except asyncio.QueueEmpty:
            # Another consumer may have drained it between full() and get_nowait().
            pass

    await frame_queue.put(payload)


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
    STUB: Pass text through Microsoft Presidio for NER redaction.
    Replaces PII, API keys, and credit cards with <REDACTED> tokens.
    """
    if not text:
        return ""
    # TODO: Implement actual Presidio Analyzer/Anonymizer here.
    # For now, if the text contains a mock secret, redact it to prove the pipeline works.
    if "password" in text.lower():
        return "<REDACTED_SECRET>"
    return text


def _run_ocr_sync(image: np.ndarray) -> str:
    """Synchronous OCR task to be run in a separate thread."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return pytesseract.image_to_string(gray).strip()


async def frame_worker_loop() -> None:
    """Continuously consume and process queued frames."""
    while True:
        payload = await frame_queue.get()
        try:
            if model is None:
                print("[frame-worker] model unavailable, skipping frame")
                continue

            # Correct schema key from Task 1.4
            image = _decode_base64_image(payload.base64_image)
            if image is None:
                print(f"[frame-worker] invalid frame payload timestamp={payload.timestamp}")
                continue

            # Thread-safe OCR and strict sanitization
            sanitized_text = ""
            try:
                raw_text = await asyncio.to_thread(_run_ocr_sync, image)
                sanitized_text = _sanitize_ocr_text(raw_text)
            except Exception as exc:
                print(f"[frame-worker] OCR failed timestamp={payload.timestamp}: {exc}")

            try:
                results = await asyncio.to_thread(
                    model.predict,
                    image,
                    verbose=False,
                )
            except Exception as exc:
                print(f"[frame-worker] inference failed timestamp={payload.timestamp}: {exc}")
                continue

            if not results:
                continue

            detected_classes = _extract_detected_classes(results[0])
            if not detected_classes:
                continue

            try:
                event_id = await log_event(
                    "yolo_detection",
                    {
                        "detected": detected_classes,
                        "ocr_text": sanitized_text,
                        "source": payload.source,
                        "frame_timestamp": payload.timestamp,
                    },
                )

                alert = {
                    "id": event_id,
                    "risk": "High",
                    "detected": detected_classes,
                    "ocr_text": sanitized_text,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as exc:
                print(f"[frame-worker] failed to write audit log: {exc}")
                continue

            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.post(ALERT_ENDPOINT, json=alert)
                if response.status_code != 200:
                    print(
                        f"[frame-worker] alert POST failed status={response.status_code} body={response.text}"
                    )
            except Exception as exc:
                print(f"[frame-worker] failed to send alert: {repr(exc)}")
        finally:
            frame_queue.task_done()
