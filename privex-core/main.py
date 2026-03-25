import asyncio
from pydantic import BaseModel
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.graph import privex_app, AgentState
from api.routes.vision import router as vision_router
from services.frame_queue import frame_worker_loop


class ChatQuery(BaseModel):
    query: str


# ✅ DEFINE FIRST
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


# ✅ THEN USE IT
app = FastAPI(title="Privex Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/chat")
async def chat_endpoint(payload: ChatQuery):
    initial_state: AgentState = {
        "user_query": payload.query,
        "current_agent": "",
        "proposed_action": "",
        "risk_level": "",
        "human_approval_required": False,
    }

    final_state = privex_app.invoke(initial_state)
    return final_state


app.include_router(vision_router)