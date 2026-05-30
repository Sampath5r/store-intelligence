#!/usr/bin/env python3
"""
CCTV Unified Person Detection & Tracking Pipeline using YOLOv8 & ByteTrack
Purplle Store Intelligence Challenge

This module provides a unified interface to perform either high-performance
person detection or stateful multi-object tracking (integrating ByteTrack)
on CCTV footage.
"""

import os
import sys
import time
import json
import logging
import argparse
from typing import Dict, List, Any, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

# ==============================================================================
# Dynamic Imports for Modular Integration
# ==============================================================================
# Setup import paths to allow executing this file directly from root or pipeline directory
try:
    from pipeline.tracker import CCTVTracker, process_video_tracking
except ImportError:
    try:
        from tracker import CCTVTracker, process_video_tracking
    except ImportError:
        # Fallback if executing from an external path or nested container
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        try:
            from tracker import CCTVTracker, process_video_tracking
        except ImportError as e:
            logging.error(f"Failed to import tracker.py. Ensure it exists in the same directory. Error: {e}")
            raise

# ==============================================================================
# Logging Configuration
# ==============================================================================
def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a standardized logger for the pipeline.
    """
    logger = logging.getLogger("CCTV_Pipeline")
    logger.setLevel(log_level)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger

logger = setup_logger()

# ==============================================================================
# Bounding Box Drawing Utilities (For Detection Mode)
# ==============================================================================
def draw_styled_bounding_box(
    frame: np.ndarray,
    box: Tuple[int, int, int, int],
    label: str,
    confidence: float,
    color: Tuple[int, int, int] = (180, 50, 180),  # Purplle Brand Primary (BGR)
    thickness: int = 2
) -> np.ndarray:
    """
    Draws a styled bounding box on the frame with rounded corner guides
    and a semi-transparent text label overlay for high visual aesthetics.
    """
    x1, y1, x2, y2 = box
    
    # Draw bounding box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness, lineType=cv2.LINE_AA)
    
    # Draw label badge
    caption = f"{label} {confidence:.2f}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    font_thickness = 1
    
    # Get text width and height
    (text_w, text_h), baseline = cv2.getTextSize(caption, font, font_scale, font_thickness)
    
    # Define badge background coordinates
    badge_x1 = x1
    badge_y1 = y1 - text_h - 6 if y1 - text_h - 6 > 0 else y1
    badge_x2 = x1 + text_w + 10
    badge_y2 = badge_y1 + text_h + 6
    
    # Draw badge background
    cv2.rectangle(frame, (badge_x1, badge_y1), (badge_x2, badge_y2), color, -1, lineType=cv2.LINE_AA)
    
    # Draw text in white on the badge background
    text_color = (255, 255, 255)
    cv2.putText(
        frame,
        caption,
        (badge_x1 + 5, badge_y2 - baseline - 2),
        font,
        font_scale,
        text_color,
        font_thickness,
        lineType=cv2.LINE_AA
    )
    
    return frame

# ==============================================================================
# Model Initialization
# ==============================================================================
def load_yolo_model(model_path: str = "yolov8n.pt", device: str = "cpu") -> YOLO:
    """
    Loads the YOLOv8 model safely on the specified device.
    """
    logger.info(f"Initializing YOLOv8 model '{model_path}' on device '{device}'...")
    try:
        start_time = time.time()
        model = YOLO(model_path)
        # Warmup run to initialize CPU graph optimizations
        model(np.zeros((640, 640, 3), dtype=np.uint8), device=device, verbose=False)
        logger.info(f"Model loaded successfully in {time.time() - start_time:.2f} seconds.")
        return model
    except Exception as e:
        logger.error(f"Failed to load YOLOv8 model from path '{model_path}'. Error: {e}")
        raise

# ==============================================================================
# Telemetry Output Management (For Detection Mode)
# ==============================================================================
def save_telemetry(detections_log: List[Dict[str, Any]], output_path: str) -> None:
    """
    Saves frame-level detection data to a structured JSON file.
    """
    logger.info(f"Saving frame-level telemetry to '{output_path}'...")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        telemetry = {
            "metadata": {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_frames_logged": len(detections_log),
                "detector_model": "YOLOv8n"
            },
            "frames": detections_log
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(telemetry, f, indent=4)
        logger.info("Telemetry data successfully written.")
    except Exception as e:
        logger.error(f"Failed to write telemetry file. Error: {e}")

# ==============================================================================
# Pure Detection Pipeline Execution
# ==============================================================================
def process_video_pipeline(
    video_path: str,
    output_video_path: str,
    output_detections_path: str,
    model: YOLO,
    conf_threshold: float = 0.25,
    device: str = "cpu"
) -> Dict[str, Any]:
    """
    Executes the standard video detection pipeline (no stateful tracking).
    Reads input video, performs frame-by-frame person detection,
    annotates video frames, and logs tracking metrics.
    """
    if not os.path.exists(video_path):
        logger.error(f"Input video file not found at path: {video_path}")
        raise FileNotFoundError(f"Input video file not found: {video_path}")
        
    logger.info(f"Opening input video stream: {video_path}")
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        logger.error("Could not open input video stream.")
        raise IOError("Could not open input video stream.")
        
    # Read video properties
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    logger.info(f"Video Properties: Resolution={frame_width}x{frame_height} | FPS={fps:.2f} | Total Frames={total_frames}")
    
    # Initialize VideoWriter
    os.makedirs(os.path.dirname(os.path.abspath(output_video_path)), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video_path, fourcc, fps, (frame_width, frame_height))
    
    if not out.isOpened():
        logger.error("Could not initialize VideoWriter.")
        cap.release()
        raise IOError("Could not initialize VideoWriter.")
        
    detections_log: List[Dict[str, Any]] = []
    frame_idx = 0
    total_persons_detected = 0
    start_processing_time = time.time()
    
    logger.info("Starting frame processing loop...")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_idx += 1
            timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            
            # Execute YOLOv8 inference (Class 0 is person)
            results = model(
                frame,
                conf=conf_threshold,
                classes=[0],
                device=device,
                verbose=False
            )
            
            # Parse detection results
            frame_detections = []
            if len(results) > 0:
                boxes = results[0].boxes
                for box in boxes:
                    xyxy = box.xyxy[0].cpu().numpy().astype(int)
                    conf = float(box.conf[0].cpu().numpy())
                    cls = int(box.cls[0].cpu().numpy())
                    
                    x1, y1, x2, y2 = xyxy
                    
                    detection_data = {
                        "bbox": [x1, y1, x2, y2],
                        "bbox_normalized": [
                            float(x1 / frame_width),
                            float(y1 / frame_height),
                            float(x2 / frame_width),
                            float(y2 / frame_height)
                        ],
                        "confidence": conf,
                        "class_id": cls
                    }
                    frame_detections.append(detection_data)
                    total_persons_detected += 1
                    
                    # Draw styled overlay on frame
                    frame = draw_styled_bounding_box(
                        frame=frame,
                        box=(x1, y1, x2, y2),
                        label="person",
                        confidence=conf
                    )
            
            # Append frame detections to overall log
            detections_log.append({
                "frame_index": frame_idx,
                "timestamp_ms": timestamp_ms,
                "person_count": len(frame_detections),
                "detections": frame_detections
            })
            
            # Write annotated frame to output video
            out.write(frame)
            
            # Log progress periodically
            if frame_idx % 50 == 0 or frame_idx == total_frames:
                elapsed = time.time() - start_processing_time
                current_fps = frame_idx / elapsed
                logger.info(
                    f"Processed {frame_idx}/{total_frames} frames | "
                    f"Current Processing Speed: {current_fps:.2f} FPS | "
                    f"Detections in current frame: {len(frame_detections)}"
                )
                
    except Exception as e:
        logger.error(f"Error encountered during video processing: {e}")
        raise
    finally:
        # Guarantee resources are freed regardless of success/error
        cap.release()
        out.release()
        logger.info("Released video streams and closed files.")
        
    total_time = time.time() - start_processing_time
    avg_fps = frame_idx / total_time if total_time > 0 else 0
    
    logger.info("==============================================================================")
    logger.info("Detection Process Finished.")
    logger.info(f"Total Frames Processed: {frame_idx}")
    logger.info(f"Total Processing Time: {total_time:.2f} seconds")
    logger.info(f"Average Execution Speed: {avg_fps:.2f} FPS")
    logger.info(f"Total Detections Logged: {total_persons_detected}")
    logger.info("==============================================================================")
    
    # Save the accumulated frame-level detection data
    save_telemetry(detections_log, output_detections_path)
    
    return {
        "total_frames": frame_idx,
        "processing_time_sec": total_time,
        "average_fps": avg_fps,
        "total_person_detections": total_persons_detected
    }

# ==============================================================================
# CLI Entrypoint & Controller Routing
# ==============================================================================
def main() -> None:
    """
    Configures and runs the unified CLI interface.
    Routes command line requests dynamically into Detection Mode or Tracking Mode.
    """
    parser = argparse.ArgumentParser(
        description="CCTV Person Detection & Stateful Multi-Object Tracking Pipeline"
    )
    parser.add_argument(
        "--video_path",
        type=str,
        required=True,
        help="Path to the input CCTV MP4 video file."
    )
    parser.add_argument(
        "--output_video_path",
        type=str,
        default="",
        help="Path to save the annotated video (defaults will automatically adjust based on mode)."
    )
    parser.add_argument(
        "--output_metadata_path",
        type=str,
        default="",
        help="Path to save frame-level telemetry JSON (defaults will automatically adjust based on mode)."
    )
    parser.add_argument(
        "--model_path",
        type=str,
        default="yolov8n.pt",
        help="Path or name of the YOLOv8 weight model (default: yolov8n.pt)."
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Confidence threshold for person filtering (default: 0.25)."
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="Execution device: 'cpu', 'cuda', etc. (default: cpu)."
    )
    parser.add_argument(
        "--track",
        action="store_true",
        help="Enable stateful Multi-Object Tracking using ByteTrack (defaults to detection only)."
    )
    
    args = parser.parse_args()
    
    # Resolve default file output paths depending on tracking vs detection selection
    if args.track:
        output_video = args.output_video_path if args.output_video_path else "data/outputs/tracked_cctv.mp4"
        output_metadata = args.output_metadata_path if args.output_metadata_path else "data/events/tracking_events.json"
    else:
        output_video = args.output_video_path if args.output_video_path else "data/outputs/detected_cctv.mp4"
        output_metadata = args.output_metadata_path if args.output_metadata_path else "data/events/detections.json"
        
    try:
        if args.track:
            logger.info("Executing pipeline in STATEFUL MULTI-OBJECT TRACKING MODE (ByteTrack)...")
            # Initialize the stateful CCTVTracker
            tracker = CCTVTracker(model_path=args.model_path, device=args.device)
            
            # Execute tracking loop (draws trajectories, displays IDs, saves video & telemetry JSON)
            process_video_tracking(
                video_path=args.video_path,
                output_video_path=output_video,
                output_events_path=output_metadata,
                tracker=tracker,
                conf_threshold=args.conf
            )
        else:
            logger.info("Executing pipeline in STANDARD DETECTION MODE (No tracking IDs)...")
            # Load basic detection model
            model = load_yolo_model(model_path=args.model_path, device=args.device)
            
            # Execute detection-only loop
            process_video_pipeline(
                video_path=args.video_path,
                output_video_path=output_video,
                output_detections_path=output_metadata,
                model=model,
                conf_threshold=args.conf,
                device=args.device
            )
            
    except Exception as e:
        logger.critical(f"Pipeline execution aborted unexpectedly. Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
