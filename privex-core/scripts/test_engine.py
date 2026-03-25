from __future__ import annotations

from pathlib import Path
import time

import numpy as np
import torch
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = PROJECT_ROOT / "models" / "yolov8n.engine"


def main() -> None:
    """Run a warmup + timed inference pass on the TensorRT engine or fallback."""
    if ENGINE_PATH.exists() and torch.cuda.is_available():
        print(f"Loading TensorRT Engine from {ENGINE_PATH}...")
        model = YOLO(str(ENGINE_PATH))
    else:
        print("WARNING: GPU/Engine not available. Falling back to standard PyTorch model (yolov8n.pt)...")
        model = YOLO("yolov8n.pt")

    dummy_image = np.zeros((640, 640, 3), dtype=np.uint8)

    # Warmup run to avoid one-time initialization skewing latency measurement.
    _ = model(dummy_image)

    start = time.perf_counter()
    results = model(dummy_image)
    end = time.perf_counter()

    latency_ms = (end - start) * 1000.0
    boxes_xyxy = results[0].boxes.xyxy.cpu().numpy()

    print(f"Inference latency: {latency_ms:.2f} ms")
    print("Raw bounding boxes (xyxy):")
    print(boxes_xyxy)


if __name__ == "__main__":
    main()
