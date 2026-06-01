#!/usr/bin/env python3
"""
CCTV Multi-Object Tracking Pipeline using YOLOv8 & ByteTrack
Purplle Store Intelligence Challenge

This module implements a CPU-optimized, consistent tracking pipeline to assign
persistent IDs to customers, handle occlusions, and map customer journey paths.
"""

import os
import sys
import time
import json
import logging
import argparse
from collections import defaultdict
from typing import Dict, List, Any, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

# ==============================================================================
# Logging Configuration
# ==============================================================================
def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a standardized logger for the tracking pipeline.
    """
    logger = logging.getLogger("CCTV_Tracker")
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
# CCTV Tracker Class
# ==============================================================================
class CCTVTracker:
    """
    Encapsulates YOLOv8 & ByteTrack tracking logic, trajectory history,
    and stylized overlay drawing capabilities.
    """
    def __init__(self, model_path: str = "yolov8n.pt", device: str = "cpu"):
        """
        Initializes the tracking model and state buffers.
        """
        logger.info(f"Loading YOLOv8 tracking model from '{model_path}' on device '{device}'...")
        try:
            self.model = YOLO(model_path)
            self.device = device
            # Warm up model
            self.model(np.zeros((640, 640, 3), dtype=np.uint8), device=self.device, verbose=False)
            
            # Journey analytics: Track the last N centroids for drawing trails
            self.track_history = defaultdict(list)
            self.max_history_len = 30
            
            # Analytical counters
            self.unique_track_ids = set()
            logger.info("Tracker initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize CCTVTracker. Error: {e}")
            raise

    def track_frame(self, frame: np.ndarray, conf_threshold: float = 0.25) -> List[Dict[str, Any]]:
        """
        Runs YOLOv8 & ByteTrack on a single frame.
        Maintains tracking state across frame sequences using model.track(persist=True).
        """
        # Run tracking. Classes=[0] restricts inference to 'person' categories.
        # tracker='bytetrack.yaml' instructs YOLOv8 to load its internal ByteTrack configuration.
        results = self.model.track(
            source=frame,
            persist=True,
            conf=conf_threshold,
            classes=[0],
            device=self.device,
            tracker="bytetrack.yaml",
            verbose=False
        )
        
        parsed_tracks = []
        if len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            
            # Check if any objects have active tracking IDs
            if boxes.id is not None:
                xyxy_list = boxes.xyxy.cpu().numpy().astype(int)
                ids_list = boxes.id.cpu().numpy().astype(int)
                conf_list = boxes.conf.cpu().numpy()
                
                for xyxy, track_id, conf in zip(xyxy_list, ids_list, conf_list):
                    x1, y1, x2, y2 = xyxy
                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)
                    
                    self.unique_track_ids.add(int(track_id))
                    
                    parsed_tracks.append({
                        "track_id": int(track_id),
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "centroid": [cx, cy],
                        "confidence": float(conf)
                    })
                    
                    # Update rolling path history
                    self.track_history[int(track_id)].append((cx, cy))
                    if len(self.track_history[int(track_id)]) > self.max_history_len:
                        self.track_history[int(track_id)].pop(0)
                        
        return parsed_tracks

    def draw_motion_paths(
        self,
        frame: np.ndarray,
        tracks: List[Dict[str, Any]],
        color: Tuple[int, int, int] = (180, 50, 180),  # Purplle Brand Primary (BGR)
        path_color: Tuple[int, int, int] = (50, 180, 50)  # Trail green (BGR)
    ) -> np.ndarray:
        """
        Draws bounding boxes, active tracking IDs, and historical trails (journey lines)
        for each tracked person on the frame.
        """
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # 1. Draw historical tracking paths (breadcrumbs)
        for track_id, points in list(self.track_history.items()):
            # Only draw path if track is active in current frame to avoid cluttering
            active_ids = [t["track_id"] for t in tracks]
            if track_id not in active_ids:
                continue
                
            if len(points) > 1:
                # Draw trailing path lines with increasing thickness/opacity
                for i in range(1, len(points)):
                    thickness = int(np.sqrt(self.max_history_len / float(i)) * 1.5)
                    cv2.line(frame, points[i-1], points[i], path_color, thickness, lineType=cv2.LINE_AA)
                    
                # Draw small circle at current position
                cv2.circle(frame, points[-1], 4, path_color, -1, lineType=cv2.LINE_AA)

        # 2. Draw styled boxes & unique tracking IDs
        for track in tracks:
            x1, y1, x2, y2 = track["bbox"]
            track_id = track["track_id"]
            conf = track["confidence"]
            
            # Outer bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, lineType=cv2.LINE_AA)
            
            # Badge text format
            badge_text = f"ID: {track_id} | person {conf:.2f}"
            font_scale = 0.45
            font_thickness = 1
            
            (text_w, text_h), baseline = cv2.getTextSize(badge_text, font, font_scale, font_thickness)
            
            # Calculate badge boundaries
            badge_x1 = x1
            badge_y1 = y1 - text_h - 6 if y1 - text_h - 6 > 0 else y1
            badge_x2 = x1 + text_w + 10
            badge_y2 = badge_y1 + text_h + 6
            
            # Badge background
            cv2.rectangle(frame, (badge_x1, badge_y1), (badge_x2, badge_y2), color, -1, lineType=cv2.LINE_AA)
            
            # Text on badge
            cv2.putText(
                frame,
                badge_text,
                (badge_x1 + 5, badge_y2 - baseline - 2),
                font,
                font_scale,
                (255, 255, 255),
                font_thickness,
                lineType=cv2.LINE_AA
            )
            
        return frame

# ==============================================================================
# Save Telemetry Function
# ==============================================================================
def save_tracking_telemetry(
    tracking_log: List[Dict[str, Any]],
    total_unique: int,
    output_path: str
) -> None:
    """
    Saves frame-by-frame tracking telemetry logs to a structured JSON file.
    """
    logger.info(f"Writing tracking events log to '{output_path}'...")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        telemetry = {
            "metadata": {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_frames_processed": len(tracking_log),
                "total_unique_customers": total_unique,
                "tracking_algorithm": "YOLOv8-ByteTrack"
            },
            "frames": tracking_log
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(telemetry, f, indent=4)
        logger.info("Tracking telemetry file successfully written.")
    except Exception as e:
        logger.error(f"Failed to save tracking telemetry. Error: {e}")

# ==============================================================================
# Pipeline Execution Driver
# ==============================================================================
def process_video_tracking(
    video_path: str,
    output_video_path: str,
    output_events_path: str,
    tracker: CCTVTracker,
    conf_threshold: float = 0.25
) -> Dict[str, Any]:
    """
    Reads an input CCTV video, runs the persistent object tracking pipeline,
    annotates the frames with trajectories, and exports spatial telemetry data.
    """
    if not os.path.exists(video_path):
        logger.error(f"Video file not found at: {video_path}")
        raise FileNotFoundError(f"Video file not found: {video_path}")
        
    logger.info(f"Opening input CCTV video: {video_path}")
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        logger.error("Could not open input video stream.")
        raise IOError("Could not open input video stream.")
        
    # Get metadata
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    logger.info(f"Source Stats: {frame_width}x{frame_height} | {fps:.2f} FPS | {total_frames} frames")
    
    # Initialize output VideoWriter
    os.makedirs(os.path.dirname(os.path.abspath(output_video_path)), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video_path, fourcc, fps, (frame_width, frame_height))
    
    if not out.isOpened():
        logger.error("Could not initialize VideoWriter output stream.")
        cap.release()
        raise IOError("Could not initialize VideoWriter.")
        
    tracking_log: List[Dict[str, Any]] = []
    frame_idx = 0
    start_time = time.time()
    
    logger.info("Executing multi-object tracking loop...")
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_idx += 1
            timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            
            # Execute stateful tracking
            tracks = tracker.track_frame(frame, conf_threshold=conf_threshold)
            
            # Add spatial coordinate scaling (normalized) to track data for downstream DBs
            frame_data_list = []
            for track in tracks:
                x1, y1, x2, y2 = track["bbox"]
                frame_data_list.append({
                    "track_id": track["track_id"],
                    "bbox": track["bbox"],
                    "bbox_normalized": [
                        float(x1 / frame_width),
                        float(y1 / frame_height),
                        float(x2 / frame_width),
                        float(y2 / frame_height)
                    ],
                    "centroid": track["centroid"],
                    "confidence": track["confidence"]
                })
                
            # Log current frame analytics
            tracking_log.append({
                "frame_index": frame_idx,
                "timestamp_ms": timestamp_ms,
                "active_count": len(frame_data_list),
                "detections": frame_data_list
            })
            
            # Render annotated frame with styled journey paths
            frame = tracker.draw_motion_paths(frame, tracks)
            
            # Write out frame
            out.write(frame)
            
            # Periodic logging
            if frame_idx % 50 == 0 or frame_idx == total_frames:
                elapsed = time.time() - start_time
                curr_fps = frame_idx / elapsed if elapsed > 0 else 0
                logger.info(
                    f"Frame {frame_idx}/{total_frames} | "
                    f"Active tracks: {len(tracks)} | "
                    f"Cumulative Customers: {len(tracker.unique_track_ids)} | "
                    f"Speed: {curr_fps:.2f} FPS"
                )
                
    except Exception as e:
        logger.error(f"Error occurred during tracking execution: {e}")
        raise
    finally:
        cap.release()
        out.release()
        logger.info("Released camera capture buffers and file writer.")
        
    total_duration = time.time() - start_time
    avg_fps = frame_idx / total_duration if total_duration > 0 else 0
    total_unique = len(tracker.unique_track_ids)
    
    logger.info("==============================================================================")
    logger.info("Tracking Process Finished.")
    logger.info(f"Total Processed Frames: {frame_idx}")
    logger.info(f"Total Unique Customers Tracked: {total_unique}")
    logger.info(f"Average Execution Speed: {avg_fps:.2f} FPS")
    logger.info("==============================================================================")
    
    # Save the output tracking telemetry JSON
    save_tracking_telemetry(tracking_log, total_unique, output_events_path)
    
    return {
        "total_frames": frame_idx,
        "processing_time_sec": total_duration,
        "average_fps": avg_fps,
        "total_unique_customers": total_unique
    }

# ==============================================================================
# CLI Entrypoint
# ==============================================================================
def main() -> None:
    """
    Configures parser args and starts multi-object tracking.
    """
    parser = argparse.ArgumentParser(
        description="CPU-optimized CCTV Multi-Object Tracking (ByteTrack) Pipeline"
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
        default="data/outputs/tracked_cctv.mp4",
        help="Path to save the trajectory-annotated MP4 video."
    )
    parser.add_argument(
        "--output_events_path",
        type=str,
        default="data/events/tracking_events.json",
        help="Path to save frame-by-frame tracking telemetry events."
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
        help="Detection confidence threshold for tracker matching (default: 0.25)."
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="Compute device: 'cpu', 'cuda', etc. (default: cpu)."
    )
    
    args = parser.parse_args()
    
    try:
        tracker = CCTVTracker(model_path=args.model_path, device=args.device)
        
        process_video_tracking(
            video_path=args.video_path,
            output_video_path=args.output_video_path,
            output_events_path=args.output_events_path,
            tracker=tracker,
            conf_threshold=args.conf
        )
    except Exception as e:
        logger.critical(f"Tracking execution aborted. Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
