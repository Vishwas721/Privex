from fastapi import APIRouter, Response, status

from core.schemas import FramePayload
from services.frame_queue import enqueue_frame

router = APIRouter()


@router.post("/api/analyze-frame", status_code=status.HTTP_202_ACCEPTED)
async def analyze_frame(payload: FramePayload) -> Response:
    await enqueue_frame(payload)
    return Response(status_code=status.HTTP_202_ACCEPTED)
