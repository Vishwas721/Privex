from pydantic import BaseModel

class FramePayload(BaseModel):
    timestamp: float
    source: str
    image_base64: str