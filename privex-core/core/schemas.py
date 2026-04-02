from pydantic import BaseModel


class FramePayload(BaseModel):
    base64_image: str
    timestamp: float
    source: str
    active_app: dict | None = None


class AlertResolution(BaseModel):
    alert_id: str
    decision: str
    timestamp: float