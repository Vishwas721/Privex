from pydantic import BaseModel

class FramePayload(BaseModel):
    timestamp: float
    source: str
    image_base64: str


class AlertResolution(BaseModel):
    alert_id: str
    decision: str
    timestamp: float