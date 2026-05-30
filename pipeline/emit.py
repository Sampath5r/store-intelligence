#!/usr/bin/env python3
"""
CCTV Event Emitter & Schema Validation
Purplle Store Intelligence Challenge

This module provides a stateful event emission layer that parses frame-level
tracking telemetry into clean retail analytics events (enter, exit, update)
and calculates customer dwell times.
"""

import os
import sys
import json
import logging
import argparse
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel, Field

# ==============================================================================
# Logging Configuration
# ==============================================================================
def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a standardized logger for the event emitter.
    """
    logger = logging.getLogger("CCTV_Emitter")
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
# Pydantic Schema Definition
# ==============================================================================
class TrackingEvent(BaseModel):
    """
    Enforces a strict, production-ready schema for CCTV retail analytics events.
    """
    timestamp: float = Field(
        ..., 
        description="Relative video timestamp in milliseconds from video start."
    )
    camera_id: str = Field(
        ..., 
        description="Unique string identifying the CCTV camera source."
    )
    track_id: int = Field(
        ..., 
        description="Persistent customer identifier assigned by the tracking pipeline."
    )
    bbox: List[int] = Field(
        ..., 
        description="Coordinates representing the bounding box [x1, y1, x2, y2]."
    )
    confidence: float = Field(
        ..., 
        description="Model confidence rating for the detection (0.0 to 1.0)."
    )
    event_type: str = Field(
        ..., 
        description="Type of telemetry event. Allowed values: 'enter', 'exit', 'update'."
    )
    dwell_time_sec: Optional[float] = Field(
        default=None, 
        description="Calculated dwell time in seconds. Populated only on 'exit' event types."
    )

# ==============================================================================
# Stateful Event Emitter
# ==============================================================================
class EventEmitter:
    """
    Statefully tracks active customer trajectories, detects zone entries/exits,
    calculates dwell time durations, and persists validated JSON events.
    """
    def __init__(self, camera_id: str, output_path: str, exit_timeout_ms: float = 2000.0):
        """
        Initializes the event emitter with camera configurations.
        """
        self.camera_id = camera_id
        self.output_path = output_path
        self.exit_timeout_ms = exit_timeout_ms
        
        # State tracking: track_id -> {entry_time_ms, last_seen_ms, last_bbox, last_conf}
        self.active_tracks: Dict[int, Dict[str, Any]] = {}
        self.emitted_events: List[TrackingEvent] = []
        
        logger.info(
            f"EventEmitter initialized for Camera ID '{camera_id}' | "
            f"Exit Timeout: {exit_timeout_ms}ms | "
            f"Output Destination: '{output_path}'"
        )
        
        # Create destination directory structure
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    def process_frame_tracks(self, tracks: List[Dict[str, Any]], timestamp_ms: float) -> List[TrackingEvent]:
        """
        Processes frame tracks, statefully registers entries/updates, 
        evaluates temporal exits, and outputs list of new events.
        """
        new_events: List[TrackingEvent] = []
        active_ids = set()
        
        # 1. Parse active detections in current frame
        for track in tracks:
            track_id = int(track["track_id"])
            bbox = [int(coord) for coord in track["bbox"]]
            confidence = float(track["confidence"])
            active_ids.add(track_id)
            
            if track_id not in self.active_tracks:
                # ENTRY EVENT: New tracking ID detected
                self.active_tracks[track_id] = {
                    "entry_time_ms": timestamp_ms,
                    "last_seen_ms": timestamp_ms,
                    "last_bbox": bbox,
                    "last_conf": confidence
                }
                event = TrackingEvent(
                    timestamp=timestamp_ms,
                    camera_id=self.camera_id,
                    track_id=track_id,
                    bbox=bbox,
                    confidence=confidence,
                    event_type="enter"
                )
                new_events.append(event)
                logger.info(
                    f"[CAMERA: {self.camera_id}] Customer ENTER | "
                    f"ID: {track_id} at {timestamp_ms:.0f}ms"
                )
            else:
                # UPDATE EVENT: Existing customer position updated
                self.active_tracks[track_id]["last_seen_ms"] = timestamp_ms
                self.active_tracks[track_id]["last_bbox"] = bbox
                self.active_tracks[track_id]["last_conf"] = confidence
                
                event = TrackingEvent(
                    timestamp=timestamp_ms,
                    camera_id=self.camera_id,
                    track_id=track_id,
                    bbox=bbox,
                    confidence=confidence,
                    event_type="update"
                )
                new_events.append(event)
                
        # 2. Check active tracks list to identify exits based on timeout threshold
        exited_ids = []
        for track_id, info in self.active_tracks.items():
            if track_id not in active_ids:
                time_since_seen = timestamp_ms - info["last_seen_ms"]
                if time_since_seen > self.exit_timeout_ms:
                    # EXIT EVENT: Customer absent past timeout
                    dwell_time = (info["last_seen_ms"] - info["entry_time_ms"]) / 1000.0  # ms to seconds
                    event = TrackingEvent(
                        timestamp=info["last_seen_ms"],  # Exit timestamp is the last frame seen
                        camera_id=self.camera_id,
                        track_id=track_id,
                        bbox=info["last_bbox"],
                        confidence=info["last_conf"],
                        event_type="exit",
                        dwell_time_sec=max(0.0, float(dwell_time))
                    )
                    new_events.append(event)
                    exited_ids.append(track_id)
                    logger.info(
                        f"[CAMERA: {self.camera_id}] Customer EXIT | "
                        f"ID: {track_id} | Dwell Time: {dwell_time:.2f}s"
                    )
                    
        # Remove exited track IDs from memory
        for track_id in exited_ids:
            del self.active_tracks[track_id]
            
        # Append and persist events list
        if new_events:
            self.emitted_events.extend(new_events)
            self.save_events()
            
        return new_events

    def flush(self, final_timestamp_ms: float) -> List[TrackingEvent]:
        """
        Emits clean 'exit' events for all remaining active customers when video ends.
        """
        new_events: List[TrackingEvent] = []
        logger.info(f"Flushing remaining tracking registers at final timestamp {final_timestamp_ms:.0f}ms...")
        
        for track_id, info in list(self.active_tracks.items()):
            dwell_time = (info["last_seen_ms"] - info["entry_time_ms"]) / 1000.0
            event = TrackingEvent(
                timestamp=info["last_seen_ms"],
                camera_id=self.camera_id,
                track_id=track_id,
                bbox=info["last_bbox"],
                confidence=info["last_conf"],
                event_type="exit",
                dwell_time_sec=max(0.0, float(dwell_time))
            )
            new_events.append(event)
            logger.info(
                f"[CAMERA: {self.camera_id}] Flush EXIT | "
                f"ID: {track_id} | Dwell Time: {dwell_time:.2f}s"
            )
            
        self.active_tracks.clear()
        if new_events:
            self.emitted_events.extend(new_events)
            self.save_events()
            
        return new_events

    def save_events(self) -> None:
        """
        Dumps the cumulative emitted events array into a clean JSON output format.
        """
        try:
            serialized = [event.model_dump() for event in self.emitted_events]
            with open(self.output_path, 'w', encoding='utf-8') as f:
                json.dump(serialized, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to persist event logs to '{self.output_path}'. Error: {e}")

# ==============================================================================
# Helper Functions
# ==============================================================================
def create_single_event(
    timestamp: float,
    camera_id: str,
    track_id: int,
    bbox: List[int],
    confidence: float,
    event_type: str,
    dwell_time_sec: Optional[float] = None
) -> TrackingEvent:
    """
    Convenience helper function to programmatically generate and validate
    a single TrackingEvent instance.
    """
    return TrackingEvent(
        timestamp=timestamp,
        camera_id=camera_id,
        track_id=track_id,
        bbox=bbox,
        confidence=confidence,
        event_type=event_type,
        dwell_time_sec=dwell_time_sec
    )

# ==============================================================================
# CLI Diagnostics Entrypoint
# ==============================================================================
def main() -> None:
    """
    CLI interface to execute diagnostic test scenarios.
    """
    parser = argparse.ArgumentParser(
        description="CCTV Analytics Event Emitter Schema & Testing"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run diagnostic mock event scenario to test schema validations."
    )
    parser.add_argument(
        "--camera_id",
        type=str,
        default="test_camera_01",
        help="Camera ID identifier to use in tests (default: test_camera_01)."
    )
    parser.add_argument(
        "--output_path",
        type=str,
        default="data/events/test_events.json",
        help="Path where diagnostic events will be saved (default: data/events/test_events.json)."
    )
    
    args = parser.parse_args()
    
    if args.test:
        logger.info("Initializing mock event sequence simulation...")
        try:
            emitter = EventEmitter(camera_id=args.camera_id, output_path=args.output_path)
            
            # Scenario Step 1: Customer ID 5 first seen (Enter)
            logger.info("Step 1: Simulating ID 5 appearance at frame timestamp 100ms...")
            tracks_f1 = [{"track_id": 5, "bbox": [100, 150, 200, 300], "confidence": 0.92}]
            emitter.process_frame_tracks(tracks_f1, timestamp_ms=100.0)
            
            # Scenario Step 2: Customer ID 5 moves (Update) and ID 10 appears (Enter)
            logger.info("Step 2: Simulating ID 5 update and ID 10 appearance at 500ms...")
            tracks_f2 = [
                {"track_id": 5, "bbox": [105, 150, 205, 300], "confidence": 0.94},
                {"track_id": 10, "bbox": [400, 200, 480, 420], "confidence": 0.88}
            ]
            emitter.process_frame_tracks(tracks_f2, timestamp_ms=500.0)
            
            # Scenario Step 3: ID 5 disappears. ID 10 updates. (Checking occlusion timer) at 3000ms
            # Time elapsed since ID 5 last seen is 3000ms - 500ms = 2500ms (> 2000ms timeout)
            logger.info("Step 3: Simulating ID 5 disappearance and ID 10 update at 3000ms...")
            tracks_f3 = [{"track_id": 10, "bbox": [410, 200, 490, 420], "confidence": 0.89}]
            emitter.process_frame_tracks(tracks_f3, timestamp_ms=3000.0)
            
            # Scenario Step 4: Final end of stream flush
            logger.info("Step 4: Simulating video completion flush at 5000ms...")
            emitter.flush(final_timestamp_ms=5000.0)
            
            logger.info(f"Verification complete. Check output event file at: {args.output_path}")
            
        except Exception as e:
            logger.critical(f"Mock validation failed. Error: {e}")
            sys.exit(1)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
