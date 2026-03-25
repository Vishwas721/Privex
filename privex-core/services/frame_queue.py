import asyncio
import base64
from datetime import datetime, timezone
from pathlib import Path
import os
import torch
import cv2
import httpx
import numpy as np
from ultralytics import YOLO

from core.schemas import FramePayload

# Bounded queue to avoid unbounded memory growth if inference stalls.
frame_queue: asyncio.Queue[FramePayload] = asyncio.Queue(maxsize=5)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = PROJECT_ROOT / "models" / "yolov8n.engine"

# Must be configurable for Docker networking (e.g., http://privex-mcp:3000/api/alert)
ALERT_ENDPOINT = os.getenv("ALERT_ENDPOINT", "http://localhost:3000/api/alert")

try:
    if ENGINE_PATH.exists() and torch.cuda.is_available():
        model = YOLO(str(ENGINE_PATH))
        print(f"[frame-worker] loaded YOLO engine: {ENGINE_PATH}")
    else:
        print("[frame-worker] GPU/Engine unavailable. Falling back to CPU PyTorch model.")
        model = YOLO("yolov8n.pt")
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


async def frame_worker_loop() -> None:
    """Continuously consume and process queued frames."""
    while True:
        payload = await frame_queue.get()
        try:
            if model is None:
                print("[frame-worker] model unavailable, skipping frame")
                continue

            image = _decode_base64_image(payload.image_base64)
            if image is None:
                print(f"[frame-worker] invalid frame payload timestamp={payload.timestamp}")
                continue

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

            alert = {
                "risk": "High",
                "detected": detected_classes,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.post(ALERT_ENDPOINT, json=alert)
                if response.status_code != 200:
                    print(
                        f"[frame-worker] alert POST failed status={response.status_code} body={response.text}"
                    )
            except Exception as exc:
                print(f"[frame-worker] failed to send alert: {exc}")
        finally:
            frame_queue.task_done()
