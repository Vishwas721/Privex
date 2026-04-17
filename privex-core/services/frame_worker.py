import asyncio
from datetime import datetime, timezone
import os
import time

import cv2
import httpx
import numpy as np

from core.database import log_event
from core.ingestion import process_and_store_memory
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
    _predict_yolo_sync,
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
_window_cache: dict[int, str] = {}  # Maps YOLO Track ID -> "SAFE", "SECRET", or "PENDING"
_window_ocr_cache: dict[int, str] = {}
_last_track_ingest_time: dict[int, float] = {}
_INGEST_INTERVAL_SECONDS = 8.0


async def _background_ocr_task(track_id: int, crop: np.ndarray):
    """Runs EasyOCR entirely in the background without blocking the main loop."""
    text = await asyncio.to_thread(_run_ocr_sync, crop)
    sanitized = _sanitize_ocr_text(text)

    # 🛑 FIX: Cache the SANITIZED text, never the raw text!
    _window_ocr_cache[track_id] = sanitized

    if _contains_trigger_words(sanitized):
        _window_cache[track_id] = "SECRET"
    else:
        _window_cache[track_id] = "SAFE"


if os.name == "nt":
    _overlay_manager: WindowsRedactionOverlayManager | _NoOpOverlayManager = WindowsRedactionOverlayManager()
    _overlay_manager.start()
else:
    _overlay_manager = _NoOpOverlayManager()


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


async def frame_worker_loop() -> None:
    """Continuously consume and process queued frames with Targeted Cropping."""
    global _window_cache, _window_ocr_cache, _last_track_ingest_time

    while True:
        payload = await frame_queue.get()
        try:
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
                results = await asyncio.to_thread(_predict_yolo_sync, image)
            except Exception as exc:
                print(f"[frame-worker] YOLO inference failed: {exc}")
                continue

            if not results or len(results[0].boxes) == 0:
                # Let the tracker coast briefly instead of instantly clearing overlays.
                stable_boxes = _tracker.update_tracks([])
                if not stable_boxes or not is_meeting_active(): # 🛡️ ENFORCED!
                    _overlay_manager.clear()
                else:
                    _overlay_manager.set_boxes(stable_boxes)

                # Fallback: Full screen OCR if YOLO found nothing, to ensure Memory Agent is fed
                now = time.time()
                last_ingest = _last_track_ingest_time.get(-1, 0.0)  # Use -1 as the "Full Screen" track ID
                if now - last_ingest >= _INGEST_INTERVAL_SECONDS:
                    print(f"👁️ [Fallback] YOLO found nothing. Running full-screen OCR...")
                    _last_track_ingest_time[-1] = now
                    # Run OCR in background on the full image
                    asyncio.create_task(_background_ocr_task(-1, image))

                    # If it was previously marked SECRET, feed it!
                    if _window_cache.get(-1) == "SECRET":
                        crop_text = _window_ocr_cache.get(-1, "")
                        if crop_text.strip():
                            active_app = ""
                            if payload.active_app and isinstance(payload.active_app, dict):
                                active_app = (payload.active_app.get("title", "") or "").strip().lower()
                            asyncio.create_task(process_and_store_memory(crop_text, active_app))
                            _window_cache[-1] = "PENDING"
                continue

            detected_classes = _extract_detected_classes(results[0])

            # 2. TARGETED CROPPING: Only OCR the exact bounding boxes YOLO found
            boxes = results[0].boxes.xyxy.cpu().numpy() if results else []
            # 🛑 NEW: Safely extract the tracking IDs generated by YOLO
            track_ids = results[0].boxes.id.int().cpu().numpy() if results and results[0].boxes.id is not None else []

            secret_boxes: list[tuple[int, int, int, int]] = []
            screen_width, screen_height = _get_primary_screen_size()
            inference_height = image.shape[0]
            inference_width = INFERENCE_WIDTH

            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = map(int, box)
                box_w = x2 - x1
                box_h = y2 - y1

                # 🛑 NEW: Async Cache Logic
                track_id = int(track_ids[i]) if i < len(track_ids) else -1
                if track_id != -1:
                    status = _window_cache.get(track_id)
                    if status == "SECRET":
                        secret_boxes.append((x1, y1, x2, y2))
                        
                        # 🧠 NEW: We must ALSO ingest secrets so the Graph Database can map them!
                        now = time.time()
                        last_ingest = _last_track_ingest_time.get(track_id, 0.0)
                        if now - last_ingest >= _INGEST_INTERVAL_SECONDS:
                            crop_text = _window_ocr_cache.get(track_id, "")
                            if crop_text.strip():
                                active_app = ""
                                if payload.active_app and isinstance(payload.active_app, dict):
                                    active_app = (payload.active_app.get("title", "") or "").strip().lower()
                                _last_track_ingest_time[track_id] = now
                                print(f"🚀 [Worker] Firing GraphRAG ingestion for SECRET in app: {active_app}")
                                asyncio.create_task(process_and_store_memory(crop_text, active_app))
                                _window_cache[track_id] = "PENDING" # Reset to read new text if user scrolls
                        continue
                    elif status in ("SAFE", "PENDING"):
                        if status == "SAFE":
                            now = time.time()
                            last_ingest = _last_track_ingest_time.get(track_id, 0.0)
                            if now - last_ingest >= _INGEST_INTERVAL_SECONDS:
                                # ⏱️ TRACER: 8-second throttle for this track reached
                                print(f"⏱️ [Worker] SAFE window tracking interval reached for Track ID {track_id}")
                                crop_text = _window_ocr_cache.get(track_id, "")
                                
                                # 🛑 NEW DEBUG PRINT: See what EasyOCR actually reads!
                                print(f"👁️ [OCR DEBUG] App: {payload.active_app.get('title', 'Unknown') if isinstance(payload.active_app, dict) else 'Unknown'} | Extracted Text: {repr(crop_text)}")
                                
                                if crop_text.strip(): # Ensured it's not just spaces
                                    active_app = ""
                                    if payload.active_app and isinstance(payload.active_app, dict):
                                        active_app = (payload.active_app.get("title", "") or "").strip().lower()
                                    _last_track_ingest_time[track_id] = now
                                    
                                    # 🚀 TRACER: Fire ingestion task
                                    print(f"🚀 [Worker] Firing process_and_store_memory for app: {active_app} with text length: {len(crop_text)}")
                                    asyncio.create_task(process_and_store_memory(crop_text, active_app))
                                    
                                    # 🛑 NEW: Reset the window to PENDING so we read the fresh text if the user scrolled!
                                    _window_cache[track_id] = "PENDING"
                        continue

                    # If we reach here, it's a brand new window!
                    # Mark it pending and fire the background OCR task without waiting.
                    _window_cache[track_id] = "PENDING"
                    h_img, w_img = image.shape[:2]
                    crop = image[max(0, y1-5):min(h_img, y2+5), max(0, x1-5):min(w_img, x2+5)]

                    # Resize massive crops to protect VRAM (INCREASED TO 1200 for OCR readability)
                    max_dim = 1200
                    if (x2-x1) > max_dim or (y2-y1) > max_dim:
                        scale = max_dim / max(x2-x1, y2-y1)
                        crop = cv2.resize(crop, (0, 0), fx=scale, fy=scale)

                    asyncio.create_task(_background_ocr_task(track_id, crop))

            sanitized_text = ""

            if not secret_boxes:
                # Update tracker with empty list so old boxes can "coast" in LOST state
                stable_boxes = _tracker.update_tracks([])
                if not stable_boxes or not is_meeting_active(): # 🛡️ ENFORCED!
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
            print("[Worker] ⏳ Calling LangGraph Memory Agent...")
            state = await asyncio.to_thread(privex_app.invoke, {
                "user_query": sanitized_text,
                "current_agent": "memory_agent",
                "proposed_action": "",
                "human_approval_required": True
            })
            print(f"[Worker] ✅ LangGraph Returned: {state.get('human_approval_required')}")

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

            # 🛡️ THE BRILLIANT COMPROMISE:
            if not is_meeting_active():
                _overlay_manager.clear()
                print("[Worker] Secret detected, but Shield is OFF (No active meeting).")
            else:
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