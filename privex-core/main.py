import asyncio
import os
import threading
from pydantic import BaseModel
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.documents import Document
import uvicorn

from core.graph import privex_app, AgentState
from core.database import close_db, get_recent_logs, init_db, log_event
from core.vector_store import init_vector_store, get_vector_store
from core.maintenance import sleep_cycle_loop
from api.routes.vision import router as vision_router
from services.frame_worker import frame_worker_loop
from os_integration.tray import run_system_tray


class ChatQuery(BaseModel):
    query: str


class ResolvePayload(BaseModel):
    alert_id: str
    decision: str
    timestamp: float
    ocr_text: str = ""


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict) -> None:
        stale: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                stale.append(connection)

        for connection in stale:
            self.disconnect(connection)


manager = ConnectionManager()


# ✅ DEFINE FIRST
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    await init_vector_store()
    try:
        await log_event("system_boot", {"message": "System Boot"})
    except Exception as exc:
        print(f"[startup] failed to write system boot audit event: {exc}")

    worker_task = asyncio.create_task(frame_worker_loop(), name="frame-worker-loop")
    sleep_cycle_task = asyncio.create_task(sleep_cycle_loop(), name="sleep-cycle")
    try:
        yield
    finally:
        worker_task.cancel()
        sleep_cycle_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        try:
            await sleep_cycle_task
        except asyncio.CancelledError:
            pass
        await close_db()


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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


@app.post("/api/chat/broadcast")
async def broadcast_alert(request: Request):
    try:
        data = await request.json()
        print("=========================================")
        print("📡 [FastAPI] Broadcast Request Received!")
        print("📦 [FastAPI] Body Type:", type(data).__name__)
        print("📦 [FastAPI] Payload Data:", data)
        print("=========================================")
        await manager.broadcast(data)
        return {"status": "success", "message": "Broadcasted to UI"}
    except Exception as e:
        print(f"❌ [FastAPI] Broadcast Error: {e}")
        return {"error": str(e)}

@app.post("/api/resolve-alert")
async def resolve_alert(payload: ResolvePayload):
    # 🧠 Teach the Memory Agent
    if payload.decision == "approved" and payload.ocr_text:
        vs = get_vector_store()
        if vs:
            doc = Document(
                page_content=payload.ocr_text,
                metadata={"approved_action": "search_local_memory", "alert_id": payload.alert_id}
            )
            await asyncio.to_thread(vs.add_documents, [doc])
            print(f"\n🧠 [Memory Agent] Learned new safe context from UI approval!\n")

    return {"status": "success"}



@app.get("/api/logs")
async def get_logs_endpoint(limit: int = 50):
    logs = await get_recent_logs(limit=limit)
    return {"logs": logs}


app.include_router(vision_router)


def _run_with_system_tray() -> None:
    shutdown_event = threading.Event()
    host = os.getenv("PRIVEX_HOST", "127.0.0.1")
    port = int(os.getenv("PRIVEX_PORT", "8000"))

    config = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)

    def _server_thread_target() -> None:
        server.run()
        shutdown_event.set()

    server_thread = threading.Thread(target=_server_thread_target, name="uvicorn-server", daemon=True)
    server_thread.start()

    def _request_shutdown() -> None:
        shutdown_event.set()
        server.should_exit = True

    try:
        # 👇 BYPASS THE TRAY ICON CRASH 👇
        print("🟢 Privex Backend Running! (Tray icon disabled to prevent Windows API crashes)")

        # Keep the main thread alive safely
        while not shutdown_event.is_set():
            import time
            time.sleep(1)

    except KeyboardInterrupt:
        pass
    finally:
        print("🔴 Shutting down server...")
        _request_shutdown()
        server_thread.join(timeout=10)


if __name__ == "__main__":
    _run_with_system_tray()