#!/usr/bin/env python3
"""
CCTV Retail Anomaly Detection Engine
Purplle Store Intelligence Challenge

This module provides modular, rule-based anomaly detection to identify overcrowding,
unusual rapid movement, long idle loitering, and restricted zone access (trespassing).
"""

import os
import sys
import uuid
import math
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Set, Any, Tuple, Optional

# Setup import paths to allow executing this file directly
try:
    from app.models import AnomalyNotification, CCTVEventPayload
except ImportError:
    try:
        from models import AnomalyNotification, CCTVEventPayload
    except ImportError:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from models import AnomalyNotification, CCTVEventPayload

# ==============================================================================
# Logging Configuration
# ==============================================================================
def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a standardized logger for the anomaly engine.
    """
    logger = logging.getLogger("CCTV_Anomalies")
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
# Default Rule Threshold Configurations
# ==============================================================================
# Busiest occupancy limits before overcrowding alerts fire
DEFAULT_CAPACITIES = {
    "billing_camera": 3,   # Small queue bottleneck limit
    "entry_camera": 4,     # Lobby congestion threshold
    "floor_camera1": 5,    # Product aisle standard load
    "floor_camera2": 5,
    "storage_area": 2      # Restricted room occupancy limit
}

# Stay limits (seconds) in zones before loitering alerts fire
DEFAULT_LOITER_LIMITS = {
    "entry_camera": 45.0,    # Shoppers should transition to floors quickly
    "storage_area": 30.0,    # Employees shouldn't loiter in storage rooms
    "billing_camera": 120.0  # Customers should not be blocked in checkout queue
}

# Restricted zone cameras off-limits to general traffic
DEFAULT_RESTRICTED_ZONES = {"storage_area"}

# Centroid velocity speed threshold (pixels per millisecond) representing running/erratic falls
DEFAULT_MAX_SPEED = 1.5

# ==============================================================================
# Rule-Based Anomaly Detectors
# ==============================================================================

def detect_overcrowding_anomalies(
    events: List[CCTVEventPayload],
    capacities: Dict[str, int] = DEFAULT_CAPACITIES,
    bin_sec: float = 10.0
) -> List[AnomalyNotification]:
    """
    Identifies overcrowding anomalies where occupancy in a specific zone
    exceeds the designated capacity within a temporal sliding window.
    """
    if not events:
        return []
        
    alerts = []
    # Group events by camera_id -> bin_idx -> set of track_ids
    bin_ms = bin_sec * 1000.0
    camera_bin_tracks = defaultdict(lambda: defaultdict(set))
    camera_bin_timestamps = defaultdict(dict)
    
    for event in events:
        bin_idx = int(event.timestamp / bin_ms)
        camera = event.camera_id
        camera_bin_tracks[camera][bin_idx].add(event.track_id)
        # Store latest actual relative timestamp of bin
        if bin_idx not in camera_bin_timestamps[camera] or event.timestamp > camera_bin_timestamps[camera][bin_idx]:
            camera_bin_timestamps[camera][bin_idx] = event.timestamp
            
    # Check capacities for each camera bin
    for camera, bins in camera_bin_tracks.items():
        limit = capacities.get(camera, 5)
        for bin_idx, tracks in bins.items():
            occupancy = len(tracks)
            if occupancy > limit:
                timestamp_ms = camera_bin_timestamps[camera][bin_idx]
                details = f"Occupancy of {occupancy} in '{camera}' exceeded capacity limit of {limit}."
                
                # Generate unique alert UUID
                alert_id = f"alert_overcrowd_{camera}_{bin_idx}"
                
                alert = AnomalyNotification(
                    alert_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, alert_id)),
                    timestamp=datetime.utcnow() - timedelta(milliseconds=timestamp_ms),
                    anomaly_type="overcrowding",
                    camera_id=camera,
                    severity="medium",
                    details=details
                )
                alerts.append(alert)
                
    return alerts


def detect_unusual_movement_anomalies(
    events: List[CCTVEventPayload],
    max_speed: float = DEFAULT_MAX_SPEED
) -> List[AnomalyNotification]:
    """
    Measures frame-by-frame velocity of bounding-box centroids for each customer.
    Flags 'unusual_movement' if velocity exceeds threshold, representing running or falling.
    """
    if not events:
        return []
        
    alerts = []
    # Group events by customer track_id
    events_by_customer = defaultdict(list)
    for event in events:
        events_by_customer[event.track_id].append(event)
        
    for track_id, cust_events in events_by_customer.items():
        # Sort chronologically
        cust_events.sort(key=lambda x: x.timestamp)
        
        for i in range(1, len(cust_events)):
            ev1 = cust_events[i-1]
            ev2 = cust_events[i]
            
            # Bounding box centers (centroids)
            x1_a, y1_a, x2_a, y2_a = ev1.bbox
            cx1 = (x1_a + x2_a) / 2.0
            cy1 = (y1_a + y2_a) / 2.0
            
            x1_b, y1_b, x2_b, y2_b = ev2.bbox
            cx2 = (x1_b + x2_b) / 2.0
            cy2 = (y1_b + y2_b) / 2.0
            
            # Coordinate distance
            dist = math.sqrt((cx2 - cx1)**2 + (cy2 - cy1)**2)
            dt_ms = ev2.timestamp - ev1.timestamp
            
            # Analyze same camera within a reasonable time gap
            if ev1.camera_id == ev2.camera_id and 0 < dt_ms < 1000.0:
                speed = dist / dt_ms  # pixels per millisecond
                
                if speed > max_speed:
                    details = (
                        f"Customer ID {track_id} registered anomalous movement velocity of "
                        f"{speed:.2f} px/ms (threshold: {max_speed:.1f} px/ms) in '{ev2.camera_id}'."
                    )
                    
                    alert_key = f"alert_speed_{track_id}_{ev2.timestamp:.0f}"
                    
                    alert = AnomalyNotification(
                        alert_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, alert_key)),
                        timestamp=datetime.utcnow() - timedelta(milliseconds=ev2.timestamp),
                        anomaly_type="unusual_movement",
                        camera_id=ev2.camera_id,
                        track_id=track_id,
                        severity="high",
                        details=details
                    )
                    alerts.append(alert)
                    
    return alerts


def detect_loitering_anomalies(
    events: List[CCTVEventPayload],
    loiter_limits: Dict[str, float] = DEFAULT_LOITER_LIMITS
) -> List[AnomalyNotification]:
    """
    Evaluates individual dwell durations per zone.
    Flags 'loitering' alerts if stay times exceed stay thresholds.
    """
    if not events:
        return []
        
    alerts = []
    # Reconstruct customer journey segments (track_id -> camera_id -> stay spans)
    # track_id -> camera_id -> list of timestamps
    track_camera_times = defaultdict(lambda: defaultdict(list))
    
    for event in events:
        track_camera_times[event.track_id][event.camera_id].append(event.timestamp)
        
    for track_id, cameras in track_camera_times.items():
        for camera, timestamps in cameras.items():
            limit_sec = loiter_limits.get(camera)
            if limit_sec is not None:
                dwell_sec = (max(timestamps) - min(timestamps)) / 1000.0
                
                if dwell_sec > limit_sec:
                    details = (
                        f"Customer ID {track_id} loitered in '{camera}' for "
                        f"{dwell_sec:.1f}s, exceeding dwell limit of {limit_sec:.0f}s."
                    )
                    
                    alert_key = f"alert_loiter_{track_id}_{camera}"
                    
                    alert = AnomalyNotification(
                        alert_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, alert_key)),
                        timestamp=datetime.utcnow() - timedelta(milliseconds=max(timestamps)),
                        anomaly_type="long_idle_duration",
                        camera_id=camera,
                        track_id=track_id,
                        severity="low",
                        details=details
                    )
                    alerts.append(alert)
                    
    return alerts


def detect_restricted_access_anomalies(
    events: List[CCTVEventPayload],
    restricted_zones: Set[str] = DEFAULT_RESTRICTED_ZONES
) -> List[AnomalyNotification]:
    """
    Detects off-limits trespassing. Flags security 'restricted_zone_access'
    if any track ID is registered on restricted camera channels.
    """
    if not events:
        return []
        
    alerts = []
    # Deduplicate alerts so we only generate one alert per trespassing session
    # track_id -> set of restricted cameras alerted
    alerted_sessions = defaultdict(set)
    
    for event in events:
        camera = event.camera_id
        track_id = event.track_id
        
        if camera in restricted_zones:
            if camera not in alerted_sessions[track_id]:
                alerted_sessions[track_id].add(camera)
                
                details = f"Unauthorized customer ID {track_id} accessed restricted zone '{camera}'."
                alert_key = f"alert_trespass_{track_id}_{camera}"
                
                alert = AnomalyNotification(
                    alert_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, alert_key)),
                    timestamp=datetime.utcnow() - timedelta(milliseconds=event.timestamp),
                    anomaly_type="restricted_zone_access",
                    camera_id=camera,
                    track_id=track_id,
                    severity="high",
                    details=details
                )
                alerts.append(alert)
                logger.warning(f"[SECURITY ALERT] Customer {track_id} accessed restricted zone: {camera}")
                
    return alerts


# ==============================================================================
# Aggregate Master Analyst
# ==============================================================================
def analyze_store_anomalies(events: List[CCTVEventPayload]) -> List[AnomalyNotification]:
    """
    Runs all rule-based anomaly engines concurrently, filters,
    and returns a sorted master list of AnomalyNotification alerts.
    """
    logger.info(f"Running anomaly detection engines on {len(events)} events...")
    
    alerts: List[AnomalyNotification] = []
    
    # 1. Overcrowding Check
    alerts.extend(detect_overcrowding_anomalies(events))
    
    # 2. Unusual Velocity Check
    alerts.extend(detect_unusual_movement_anomalies(events))
    
    # 3. Loitering Stay Check
    alerts.extend(detect_loitering_anomalies(events))
    
    # 4. Trespassing / Restricted Access Check
    alerts.extend(detect_restricted_access_anomalies(events))
    
    # Sort alerts chronologically (oldest to newest)
    alerts.sort(key=lambda x: x.timestamp)
    
    logger.info(f"Anomaly analysis complete. Generated {len(alerts)} system alerts.")
    return alerts
