from typing import Any, Dict, Optional

from pydantic import BaseModel


class FramePayload(BaseModel):
    """Payload schema for sampled screen frames from the UI client."""

    base64_image: str
    timestamp: float
    source: Optional[str] = None
    active_app: Optional[Dict[str, Any]] = None


class AlertResolution(BaseModel):
    alert_id: str
    decision: str
    timestamp: float