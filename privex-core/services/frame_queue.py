import asyncio
import base64
from datetime import datetime, timezone
from pathlib import Path
import os
import re
import torch
import cv2
import httpx
import numpy as np
import pytesseract
from ultralytics import YOLO

from core.database import log_event
from core.schemas import FramePayload
from core.graph import privex_app

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
    
    # FORCE YOLO ONTO THE GPU
    model.to("cuda")
    
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


async def frame_worker_loop() -> None:
    """Continuously consume and process queued frames with Targeted Cropping."""
    while True:
        payload = await frame_queue.get()
        try:
            if model is None:
                continue

            image = _decode_base64_image(payload.base64_image)
            if image is None:
                continue
            
            # 0. THE MIRROR BYPASS: Don't police the police!
            active_app_title = ""
            if payload.active_app and isinstance(payload.active_app, dict):
               active_app_title = payload.active_app.get("title", "").lower()

            if "privex-ui" in active_app_title or "localhost:5173" in active_app_title or "security console" in active_app_title:
               continue  # Skip this frame entirely!

            # 1. VISION FIRST: Let YOLO find the windows/objects
            try:
                results = await asyncio.to_thread(model.predict, image, verbose=False)
            except Exception as exc:
                print(f"[frame-worker] YOLO inference failed: {exc}")
                continue

            if not results or len(results[0].boxes) == 0:
                continue # Nothing detected on screen, skip entirely.

            detected_classes = _extract_detected_classes(results[0])

            # 2. TARGETED CROPPING: Only OCR the exact bounding boxes YOLO found
            raw_text_chunks = []
            boxes = results[0].boxes.xyxy.cpu().numpy() # Get coordinates: [x1, y1, x2, y2]
            
            for box in boxes:
                x1, y1, x2, y2 = map(int, box)
                # Crop the OpenCV image array to just the bounding box (with 5px padding)
                h, w = image.shape[:2]
                crop = image[max(0, y1-5):min(h, y2+5), max(0, x1-5):min(w, x2+5)]
                
                if crop.size > 0:
                    text = await asyncio.to_thread(_run_ocr_sync, crop)
                    if text.strip():
                        raw_text_chunks.append(text.strip())

            # Combine the text from all the cropped boxes
            combined_raw_text = " | ".join(raw_text_chunks)
            
            # 3. REDACT & FILTER
            sanitized_text = _sanitize_ocr_text(combined_raw_text)

            lower_text = sanitized_text.lower()
            trigger_words = ["password", "api", "secret", "confidential", "private", ".env", "key"]
            if not any(word in lower_text for word in trigger_words):
                continue # Drop frame if no secrets found in the cropped areas
            
            # 4. LOG & ALERT (The rest remains exactly the same!)
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
                "active_app": getattr(payload, "active_app", None),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Ask the Memory Agent before alerting
            state = await asyncio.to_thread(privex_app.invoke, {
                "user_query": sanitized_text,
                "current_agent": "memory_agent",
                "proposed_action": "",
                "human_approval_required": True
            })

            if state.get("human_approval_required") is False:
                print(f"\n🧠 [Memory Agent] Auto-approved recognized context. Suppressing alert!\n")
                continue 

            print(f"\n[🚀 OUTGOING ALERT] App: {alert.get('active_app')} | OCR: {alert.get('ocr_text')}\n")
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(ALERT_ENDPOINT, json=alert)

        except Exception as exc:
            print(f"[frame-worker] loop error: {exc}")
        finally:
            frame_queue.task_done()
