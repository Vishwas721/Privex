import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes.vision import router as vision_router
from services.frame_queue import frame_worker_loop


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    worker_task = asyncio.create_task(frame_worker_loop(), name="frame-worker-loop")
    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Privex Backend", lifespan=lifespan)
app.include_router(vision_router)
