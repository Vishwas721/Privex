from __future__ import annotations

import os
from pathlib import Path

import torch
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"
WEIGHTS_NAME = "yolov8n.pt"


def main() -> None:
    """Export YOLOv8 nano weights to a TensorRT FP16 engine."""
    if not torch.cuda.is_available():
        print("WARNING: CUDA not detected. Skipping TensorRT export (CPU fallback mode).")
        return

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Ultralytics downloads known assets (like yolov8n.pt) into the current
    # working directory if they do not exist, so we switch into models/ first.
    previous_cwd = Path.cwd()
    os.chdir(MODELS_DIR)
    try:
        model = YOLO(WEIGHTS_NAME)
    finally:
        os.chdir(previous_cwd)

    engine_path = model.export(
    format="engine",
    half=True,
    imgsz=640,
    workspace=4,
    )

# Move to models dir
    target_path = MODELS_DIR / "yolov8n.engine"
    Path(engine_path).rename(target_path)

    print(f"Saved at {target_path}")


if __name__ == "__main__":
    main()
