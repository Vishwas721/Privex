import time

from fastapi import APIRouter, Response, status

from core.database import log_event
from core.schemas import AlertResolution, FramePayload
from services.frame_worker import enqueue_frame

router = APIRouter()


@router.post("/api/analyze-frame", status_code=status.HTTP_202_ACCEPTED)
async def analyze_frame(payload: FramePayload) -> Response:
    receive_start = time.perf_counter()
    await enqueue_frame(payload)
    receive_end = time.perf_counter()
    print(f"[⏱️ Profiler] FastAPI Network Receive -> Queue: {(receive_end - receive_start) * 1000:.2f} ms")
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/api/resolve-alert", status_code=status.HTTP_200_OK)
async def resolve_alert(payload: AlertResolution) -> dict[str, str]:
    await log_event(
        event_type="human_decision",
        details={
            "alert_id": payload.alert_id,
            "decision": payload.decision,
            "client_timestamp": payload.timestamp,
        },
    )
    return {"status": "success"}
