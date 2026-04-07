import asyncio
from datetime import datetime, timezone
import os

import httpx

from core.database import log_event
from core.schemas import FramePayload
from core.graph import privex_app
from os_integration.overlay import (
    _NoOpOverlayManager,
    WindowsRedactionOverlayManager,
    _get_primary_screen_size,
    _scale_overlay_boxes,
)
from os_integration.meeting_hook import is_meeting_active
from vision.engine import (
    INFERENCE_WIDTH,
    _contains_trigger_words,
    _decode_base64_image,
    _extract_detected_classes,
    _run_ocr_sync,
    _sanitize_ocr_text,
    model,
)
from vision.tracker import TrackManager


# 🛑 FIX: Change maxsize to 1. This forces real-time processing and kills the 10-second delay!
frame_queue: asyncio.Queue[FramePayload] = asyncio.Queue(maxsize=1)

# Must be configurable for Docker networking (e.g., http://privex-mcp:3000/api/alert)
ALERT_ENDPOINT = os.getenv("ALERT_ENDPOINT", "http://127.0.0.1:3000/api/alert")

# Initialize the global tracker
_tracker = TrackManager()


if os.name == "nt":
    _overlay_manager: WindowsRedactionOverlayManager | _NoOpOverlayManager = WindowsRedactionOverlayManager()
    _overlay_manager.start()
else:
    _overlay_manager = _NoOpOverlayManager()


async def enqueue_frame(payload: FramePayload) -> None:
    """Enqueue newest frame; drop oldest when queue is full for real-time behavior."""
    if not is_meeting_active():
        return

    if frame_queue.full():
        try:
            frame_queue.get_nowait()  # Aggressively drop oldest frame.
            frame_queue.task_done()
        except asyncio.QueueEmpty:
            # Another consumer may have drained it between full() and get_nowait().
            pass

    await frame_queue.put(payload)


async def frame_worker_loop() -> None:
    """Continuously consume and process queued frames with Targeted Cropping."""

    while True:
        payload = await frame_queue.get()
        try:
            if not is_meeting_active():
                _overlay_manager.clear()
                _tracker.tracks = []
                continue

            if model is None:
                _overlay_manager.clear()
                continue

            image = _decode_base64_image(payload.base64_image)
            if image is None:
                _overlay_manager.clear()
                continue

            # 0. THE MIRROR BYPASS: Don't police the police!
            active_app_title = ""
            if payload.active_app and isinstance(payload.active_app, dict):
               active_app_title = payload.active_app.get("title", "").lower()

            # NEW: Add your AI tools to the ignore list
            ignore_list = ["privex-ui", "localhost:5173", "security console", "gemini", "chatgpt", "claude"]
            if any(ignored in active_app_title for ignored in ignore_list):
                 _overlay_manager.clear()
                 continue  # Skip this frame entirely!

            # 1. VISION FIRST: Let YOLO find the windows/objects
            try:
                results = await asyncio.to_thread(model.predict, image, verbose=False)
            except Exception as exc:
                print(f"[frame-worker] YOLO inference failed: {exc}")
                continue

            if not results or len(results[0].boxes) == 0:
                # Let the tracker coast briefly instead of instantly clearing overlays.
                stable_boxes = _tracker.update_tracks([])
                if not stable_boxes:
                    _overlay_manager.clear()
                else:
                    _overlay_manager.set_boxes(stable_boxes)
                continue

            detected_classes = _extract_detected_classes(results[0])

            # 2. TARGETED CROPPING: Only OCR the exact bounding boxes YOLO found
            raw_text_chunks = []
            secret_boxes: list[tuple[int, int, int, int]] = []
            boxes = results[0].boxes.xyxy.cpu().numpy() # Get coordinates: [x1, y1, x2, y2]
            screen_width, screen_height = _get_primary_screen_size()
            inference_height = image.shape[0]
            inference_width = INFERENCE_WIDTH

            for box in boxes:
                x1, y1, x2, y2 = map(int, box)
                box_w = x2 - x1
                box_h = y2 - y1
                # 🛑 FIX: Ignore large background windows (like VS Code). Only redact smaller floating windows (like Notepad).
                if box_w > (inference_width * 0.95) or box_h > (inference_height * 0.95):
                    continue

                # Crop the OpenCV image array to just the bounding box (with 5px padding)
                h, w = image.shape[:2]
                crop = image[max(0, y1-5):min(h, y2+5), max(0, x1-5):min(w, x2+5)]

                if crop.size > 0:
                    text = await asyncio.to_thread(_run_ocr_sync, crop)
                    if text.strip():
                        chunk_text = text.strip()
                        raw_text_chunks.append(chunk_text)

                        # Only redact specific crops that triggered the secret filter.
                        sanitized_chunk = _sanitize_ocr_text(chunk_text)
                        if _contains_trigger_words(sanitized_chunk):
                            secret_boxes.append((x1, y1, x2, y2))

            # Combine the text from all the cropped boxes
            combined_raw_text = " | ".join(raw_text_chunks)

            # 3. REDACT & FILTER
            sanitized_text = _sanitize_ocr_text(combined_raw_text)

            if not secret_boxes:
                # Update tracker with empty list so old boxes can "coast" in LOST state
                stable_boxes = _tracker.update_tracks([])
                if not stable_boxes:
                    _overlay_manager.clear()
                else:
                    _overlay_manager.set_boxes(stable_boxes)
                continue # Drop frame if no secrets found to avoid spamming alerts

            # 4. LOG & ALERT
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
                _overlay_manager.clear()
                print(f"\n🧠 [Memory Agent] Auto-approved recognized context. Suppressing alert!\n")
                continue

            scaled_secret_boxes = _scale_overlay_boxes(
                secret_boxes,
                screen_width=screen_width,
                screen_height=screen_height,
                inference_width=inference_width,
                inference_height=inference_height,
            )

            # 🧠 NEW: Pass the raw boxes through the State Machine
            stable_boxes = _tracker.update_tracks(scaled_secret_boxes)

            # Send the smoothed, stateful boxes to the GUI
            if not stable_boxes:
                _overlay_manager.clear()
            else:
                _overlay_manager.set_boxes(stable_boxes)

            print(f"\n[🚀 OUTGOING ALERT] App: {alert.get('active_app')} | OCR: {alert.get('ocr_text')}\n")
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(ALERT_ENDPOINT, json=alert)

        except Exception as exc:
            _overlay_manager.clear()
            print(f"[frame-worker] loop error: {exc}")
        finally:
            frame_queue.task_done()