#!/usr/bin/env python3
"""
CCTV Retail Analytics Metrics Engine
Purplle Store Intelligence Challenge

This module provides modular, CPU-optimized analytical functions to compute
people counts, live active visitors, dwell-time analytics, peak traffic,
customer spatial-temporal trajectories, and busiest camera zones.
"""

import os
import sys
import logging
from collections import defaultdict
from typing import List, Dict, Set, Any, Tuple, Optional
import numpy as np

# Setup import paths to allow executing this file directly
try:
    from app.models import CCTVEventPayload
except ImportError:
    try:
        from models import CCTVEventPayload
    except ImportError:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from models import CCTVEventPayload

# ==============================================================================
# Logging Configuration
# ==============================================================================
def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a standardized logger for the metrics engine.
    """
    logger = logging.getLogger("CCTV_Metrics")
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
# Modular Analytics Functions
# ==============================================================================

def get_total_unique_customers(events: List[CCTVEventPayload]) -> int:
    """
    Computes the total number of unique customers detected across the stream.
    """
    if not events:
        return 0
    unique_ids = {e.track_id for e in events}
    return len(unique_ids)


def get_active_visitors(events: List[CCTVEventPayload]) -> List[int]:
    """
    Identifies currently active visitors (occupancy).
    A visitor is active if their last registered event is NOT an 'exit'.
    Returns a list of active track IDs.
    """
    if not events:
        return []
        
    # Group events by track ID and find the chronologically latest event for each
    latest_event_by_track: Dict[int, CCTVEventPayload] = {}
    for event in events:
        track_id = event.track_id
        if track_id not in latest_event_by_track:
            latest_event_by_track[track_id] = event
        else:
            if event.timestamp > latest_event_by_track[track_id].timestamp:
                latest_event_by_track[track_id] = event
                
    active_tracks = []
    for track_id, last_event in latest_event_by_track.items():
        if last_event.event_type != "exit":
            active_tracks.append(track_id)
            
    return active_tracks


def calculate_dwell_analytics(events: List[CCTVEventPayload]) -> Dict[str, Any]:
    """
    Computes dwell-time metrics, averages, medians, and distribution ranges.
    """
    if not events:
        return {
            "average_dwell_time_sec": 0.0,
            "median_dwell_time_sec": 0.0,
            "total_customers_measured": 0,
            "dwell_time_distribution": {}
        }
        
    dwell_times: List[float] = []
    
    # 1. Collect pre-computed dwell times from explicit exit events
    for event in events:
        if event.event_type == "exit" and event.dwell_time_sec is not None:
            dwell_times.append(event.dwell_time_sec)
            
    # 2. Fallback: If no explicit exit events exist, compute dwell times using duration spans
    if not dwell_times:
        logger.debug("No explicit 'exit' dwell times found. Falling back to duration span calculations.")
        track_spans = defaultdict(list)
        for event in events:
            track_spans[event.track_id].append(event.timestamp)
            
        for track_id, timestamps in track_spans.items():
            span_ms = max(timestamps) - min(timestamps)
            dwell_times.append(span_ms / 1000.0) # convert to seconds
            
    if not dwell_times:
        return {
            "average_dwell_time_sec": 0.0,
            "median_dwell_time_sec": 0.0,
            "total_customers_measured": 0,
            "dwell_time_distribution": {}
        }
        
    # Calculate statistical metrics
    dwell_array = np.array(dwell_times)
    avg_dwell = float(np.mean(dwell_array))
    median_dwell = float(np.median(dwell_array))
    
    # Build distribution buckets
    distribution = {
        "< 15s": 0,
        "15s - 1m": 0,
        "1m - 3m": 0,
        "3m - 5m": 0,
        "> 5m": 0
    }
    
    for dwell in dwell_times:
        if dwell < 15.0:
            distribution["< 15s"] += 1
        elif dwell < 60.0:
            distribution["15s - 1m"] += 1
        elif dwell < 180.0:
            distribution["1m - 3m"] += 1
        elif dwell < 300.0:
            distribution["3m - 5m"] += 1
        else:
            distribution["> 5m"] += 1
            
    return {
        "average_dwell_time_sec": round(avg_dwell, 2),
        "median_dwell_time_sec": round(median_dwell, 2),
        "total_customers_measured": len(dwell_times),
        "dwell_time_distribution": distribution
    }


def get_peak_traffic_periods(
    events: List[CCTVEventPayload], 
    interval_sec: float = 30.0
) -> List[Dict[str, Any]]:
    """
    Groups events into equal temporal bins and counts unique customers active
    during each bin to locate peak traffic periods.
    """
    if not events:
        return []
        
    # Maps bin_index -> set of track_ids
    bin_occupancy = defaultdict(set)
    interval_ms = interval_sec * 1000.0
    
    for event in events:
        bin_idx = int(event.timestamp / interval_ms)
        bin_occupancy[bin_idx].add(event.track_id)
        
    traffic_periods = []
    for bin_idx, tracks in bin_occupancy.items():
        start_time_sec = (bin_idx * interval_ms) / 1000.0
        end_time_sec = start_time_sec + interval_sec
        traffic_periods.append({
            "bin_index": bin_idx,
            "start_time_readable": f"{int(start_time_sec // 60):02d}:{int(start_time_sec % 60):02d}",
            "time_range": f"{start_time_sec:.1f}s - {end_time_sec:.1f}s",
            "visitor_count": len(tracks)
        })
        
    # Sort bins chronologically
    traffic_periods.sort(key=lambda x: x["bin_index"])
    return traffic_periods


def reconstruct_customer_trajectories(events: List[CCTVEventPayload]) -> Dict[int, List[Dict[str, Any]]]:
    """
    Reconstructs the chronological movement path and dwell history of each customer ID
    across different camera zones.
    """
    if not events:
        return {}
        
    # Group events by customer ID
    events_by_customer = defaultdict(list)
    for event in events:
        events_by_customer[event.track_id].append(event)
        
    trajectories = {}
    for track_id, cust_events in events_by_customer.items():
        # Sort events chronologically
        cust_events.sort(key=lambda x: x.timestamp)
        
        journey = []
        current_zone: Optional[str] = None
        entered_at: float = 0.0
        
        for idx, event in enumerate(cust_events):
            camera = event.camera_id
            
            # Transition triggers if customer moves to a new camera view
            if current_zone is None:
                current_zone = camera
                entered_at = event.timestamp
            elif current_zone != camera:
                # Log completed transit in previous zone
                exit_at = event.timestamp
                dwell = (exit_at - entered_at) / 1000.0
                journey.append({
                    "camera_id": current_zone,
                    "entered_at_ms": entered_at,
                    "left_at_ms": exit_at,
                    "dwell_time_sec": round(max(0.0, dwell), 2)
                })
                # Set up next zone
                current_zone = camera
                entered_at = event.timestamp
                
            # If explicit exit event is registered, close the final zone transit
            if event.event_type == "exit":
                dwell = (event.timestamp - entered_at) / 1000.0
                journey.append({
                    "camera_id": current_zone,
                    "entered_at_ms": entered_at,
                    "left_at_ms": event.timestamp,
                    "dwell_time_sec": round(max(0.0, dwell), 2)
                })
                current_zone = None
                
        # Safe closure if customer didn't register an exit event
        if current_zone is not None and cust_events:
            final_time = cust_events[-1].timestamp
            dwell = (final_time - entered_at) / 1000.0
            journey.append({
                "camera_id": current_zone,
                "entered_at_ms": entered_at,
                "left_at_ms": final_time,
                "dwell_time_sec": round(max(0.0, dwell), 2)
            })
            
        trajectories[track_id] = journey
        
    return trajectories


def get_camera_traffic_breakdown(events: List[CCTVEventPayload]) -> List[Dict[str, Any]]:
    """
    Ranks store cameras based on event frequency and unique customer volumes.
    Highlights which zones are the busiest.
    """
    if not events:
        return []
        
    camera_events = defaultdict(int)
    camera_visitors = defaultdict(set)
    
    for event in events:
        camera = event.camera_id
        camera_events[camera] += 1
        camera_visitors[camera].add(event.track_id)
        
    breakdown = []
    for camera in camera_events.keys():
        unique_visitors = len(camera_visitors[camera])
        total_signals = camera_events[camera]
        breakdown.append({
            "camera_id": camera,
            "unique_visitors": unique_visitors,
            "total_detections": total_signals,
            "signals_per_visitor": round(total_signals / unique_visitors, 1) if unique_visitors > 0 else 0
        })
        
    # Sort cameras from busiest to quietest (by unique visitors, then detections)
    breakdown.sort(key=lambda x: (x["unique_visitors"], x["total_detections"]), reverse=True)
    return breakdown


# ==============================================================================
# Aggregate Master Compiler
# ==============================================================================
def compile_dashboard_summary(events: List[CCTVEventPayload]) -> Dict[str, Any]:
    """
    Aggregates all modular metrics computations into a single structured dictionary
    suitable for feeding dashboards or API endpoints.
    """
    logger.info(f"Compiling batch analytics summary from {len(events)} telemetry events...")
    
    total_unique = get_total_unique_customers(events)
    active_visitors = get_active_visitors(events)
    dwell_stats = calculate_dwell_analytics(events)
    traffic_periods = get_peak_traffic_periods(events, interval_sec=30.0)
    camera_breakdown = get_camera_traffic_breakdown(events)
    
    # Identify busiest camera
    busiest_cam = camera_breakdown[0]["camera_id"] if camera_breakdown else "N/A"
    
    # Identify peak occupancy value
    peak_visitor_count = max([t["visitor_count"] for t in traffic_periods]) if traffic_periods else 0
    peak_ranges = [t["time_range"] for t in traffic_periods if t["visitor_count"] == peak_visitor_count]
    peak_time_readable = peak_ranges[0] if peak_ranges else "N/A"
    
    summary = {
        "metadata": {
            "total_events_processed": len(events),
            "timestamp": logger.name
        },
        "kpis": {
            "total_unique_customers": total_unique,
            "active_occupancy": len(active_visitors),
            "average_dwell_time_sec": dwell_stats["average_dwell_time_sec"],
            "median_dwell_time_sec": dwell_stats["median_dwell_time_sec"],
            "busiest_camera_zone": busiest_cam,
            "peak_traffic_count": peak_visitor_count,
            "peak_traffic_period": peak_time_readable
        },
        "dwell_distribution": dwell_stats["dwell_time_distribution"],
        "traffic_timeline": traffic_periods,
        "camera_rankings": camera_breakdown
    }
    
    logger.info("Batch metrics compilation complete.")
    return summary
