import asyncio

from core.schemas import FramePayload

# Bounded queue to avoid unbounded memory growth if inference stalls.
frame_queue: asyncio.Queue[FramePayload] = asyncio.Queue(maxsize=5)


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
    """Continuously consume and process queued frames."""
    while True:
        payload = await frame_queue.get()
        try:
            print(f"[frame-worker] processing frame timestamp={payload.timestamp}")
            # IMPORTANT: Future YOLOv8 TensorRT inference MUST be executed via
            # asyncio.to_thread(...) so synchronous GPU/CPU calls do not block
            # the FastAPI event loop.
            await asyncio.sleep(0.1)
        finally:
            frame_queue.task_done()
