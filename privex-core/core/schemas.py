from pydantic import BaseModel


class FramePayload(BaseModel):
    """Payload schema for sampled screen frames from the UI client."""

    base64_image: str
    timestamp: float
