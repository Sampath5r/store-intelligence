#!/usr/bin/env python3
"""
Unified CCTV Person Detection & Tracking Pipeline
Purplle Store Intelligence Challenge

Features:
- YOLOv8 person detection
- Optional ByteTrack tracking
- Dynamic multi-camera output naming
- JSON telemetry/event generation
- CPU optimized
- Modular architecture
- Clean logging
"""

import os
import sys
import cv2
import json
import time
import argparse
import logging
from typing import Dict, List, Any

import numpy as np
from ultralytics import YOLO

# ==============================================================================
# Dynamic Tracker Import
# ==============================================================================

try:
    from pipeline.tracker import CCTVTracker, process_video_tracking
except ImportError:
    try:
        from tracker import CCTVTracker, process_video_tracking
    except ImportError:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from tracker import CCTVTracker, process_video_tracking

# ==============================================================================
# Logger Configuration
# ==============================================================================

def setup_logger() -> logging.Logger:
    logger = logging.getLogger("CCTVPipeline")

    if not logger.handlers:
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stdout)

        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger()

# ==============================================================================
# Utility Functions
# ==============================================================================

def ensure_directories() -> None:
    """
    Ensure required directories exist.
    """

    os.makedirs("data/outputs", exist_ok=True)
    os.makedirs("data/events", exist_ok=True)
    os.makedirs("data/logs", exist_ok=True)


def get_camera_name(video_path: str) -> str:
    """
    Extract camera/video filename without extension.
    """

    return os.path.splitext(os.path.basename(video_path))[0]


def draw_detection_box(
    frame: np.ndarray,
    bbox: List[int],
    confidence: float,
    color=(180, 50, 180)
) -> np.ndarray:
    """
    Draw styled bounding box.
    """

    x1, y1, x2, y2 = bbox

    cv2.rectangle(
        frame,
        (x1, y1),
        (x2, y2),
        color,
        2
    )

    label = f"Person {confidence:.2f}"

    cv2.putText(
        frame,
        label,
        (x1, max(y1 - 10, 20)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        2
    )

    return frame

# ==============================================================================
# YOLO Model Loading
# ==============================================================================

def load_model(
    model_path: str,
    device: str
) -> YOLO:
    """
    Load YOLOv8 model.
    """

    logger.info(f"Loading YOLO model: {model_path}")

    try:
        model = YOLO(model_path)

        # Warmup
        model(
            np.zeros((640, 640, 3), dtype=np.uint8),
            device=device,
            verbose=False
        )

        logger.info("YOLO model initialized successfully.")

        return model

    except Exception as e:
        logger.error(f"Model loading failed: {e}")
        raise

# ==============================================================================
# Telemetry Saving
# ==============================================================================

def save_telemetry(
    telemetry_data: List[Dict[str, Any]],
    output_path: str
) -> None:
    """
    Save frame-level detections.
    """

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "metadata": {
                        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "total_frames": len(telemetry_data)
                    },
                    "frames": telemetry_data
                },
                f,
                indent=4
            )

        logger.info(f"Telemetry saved: {output_path}")

    except Exception as e:
        logger.error(f"Failed to save telemetry: {e}")

# ==============================================================================
# Detection Pipeline
# ==============================================================================

def process_video_detection(
    video_path: str,
    output_video_path: str,
    output_json_path: str,
    model: YOLO,
    confidence_threshold: float,
    device: str
) -> Dict[str, Any]:
    """
    Process CCTV video using YOLO detection.
    """

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    logger.info(f"Opening video: {video_path}")

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise IOError("Unable to open video.")

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    logger.info(
        f"Resolution={frame_width}x{frame_height} | "
        f"FPS={fps:.2f} | "
        f"Frames={total_frames}"
    )

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    writer = cv2.VideoWriter(
        output_video_path,
        fourcc,
        fps,
        (frame_width, frame_height)
    )

    telemetry = []

    frame_index = 0
    total_detections = 0

    start_time = time.time()

    while True:

        ret, frame = cap.read()

        if not ret:
            break

        frame_index += 1

        results = model(
            frame,
            conf=confidence_threshold,
            classes=[0],
            device=device,
            verbose=False
        )

        frame_detections = []

        if len(results) > 0:

            boxes = results[0].boxes

            for box in boxes:

                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                conf = float(box.conf[0].cpu().numpy())

                x1, y1, x2, y2 = xyxy.tolist()

                bbox = [x1, y1, x2, y2]

                frame_detections.append({
                    "bbox": bbox,
                    "confidence": conf
                })

                total_detections += 1

                frame = draw_detection_box(
                    frame,
                    bbox,
                    conf
                )

        telemetry.append({
            "frame_index": frame_index,
            "timestamp_ms": cap.get(cv2.CAP_PROP_POS_MSEC),
            "person_count": len(frame_detections),
            "detections": frame_detections
        })

        writer.write(frame)

        if frame_index % 50 == 0 or frame_index == total_frames:

            elapsed = time.time() - start_time

            processing_fps = frame_index / elapsed

            logger.info(
                f"Processed {frame_index}/{total_frames} "
                f"| Speed={processing_fps:.2f} FPS "
                f"| Persons={len(frame_detections)}"
            )

    cap.release()
    writer.release()

    total_time = time.time() - start_time

    logger.info("====================================================")
    logger.info("Detection pipeline completed successfully.")
    logger.info(f"Frames Processed: {frame_index}")
    logger.info(f"Total Detections: {total_detections}")
    logger.info(f"Processing Time: {total_time:.2f} sec")
    logger.info("====================================================")

    save_telemetry(telemetry, output_json_path)

    return {
        "frames_processed": frame_index,
        "total_detections": total_detections,
        "processing_time_sec": total_time
    }

# ==============================================================================
# Main Entrypoint
# ==============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description="Unified CCTV Detection & Tracking Pipeline"
    )

    parser.add_argument(
        "--video_path",
        type=str,
        required=True,
        help="Input CCTV video path"
    )

    parser.add_argument(
        "--model_path",
        type=str,
        default="yolov8n.pt",
        help="YOLOv8 model path"
    )

    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Confidence threshold"
    )

    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="Execution device"
    )

    parser.add_argument(
        "--track",
        action="store_true",
        help="Enable ByteTrack tracking"
    )

    args = parser.parse_args()

    ensure_directories()

    camera_name = get_camera_name(args.video_path)

    # Dynamic output naming - use simple camera-based filenames
    output_video_path = f"data/outputs/{camera_name}_output.mp4"
    output_json_path = f"data/events/{camera_name}_events.json"

    logger.info("====================================================")
    logger.info(f"Camera: {camera_name}")
    logger.info(f"Input Video: {args.video_path}")
    logger.info(f"Output Video: {output_video_path}")
    logger.info(f"Telemetry JSON: {output_json_path}")
    logger.info("====================================================")

    try:

        if args.track:

            logger.info("Running in TRACKING MODE")

            tracker = CCTVTracker(
                model_path=args.model_path,
                device=args.device
            )

            process_video_tracking(
                video_path=args.video_path,
                output_video_path=output_video_path,
                output_events_path=output_json_path,
                tracker=tracker,
                conf_threshold=args.conf
            )

        else:

            logger.info("Running in DETECTION MODE")

            model = load_model(
                model_path=args.model_path,
                device=args.device
            )

            process_video_detection(
                video_path=args.video_path,
                output_video_path=output_video_path,
                output_json_path=output_json_path,
                model=model,
                confidence_threshold=args.conf,
                device=args.device
            )

    except Exception as e:

        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()