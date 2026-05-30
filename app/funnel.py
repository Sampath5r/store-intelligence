#!/usr/bin/env python3
"""
CCTV Customer Session & Retail Funnel Analytics Engine
Purplle Store Intelligence Challenge

This module provides stateful customer session reconstruction, spatial funnel stage
mapping, dropout/abandonment analysis, and transition efficiency metrics.
"""

import os
import sys
import logging
from collections import defaultdict
from typing import List, Dict, Set, Any, Tuple, Optional

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
    Sets up a standardized logger for the funnel engine.
    """
    logger = logging.getLogger("CCTV_Funnel")
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
# Funnel Stage Mapping Definitions
# ==============================================================================
# Map CCTV camera identifiers to retail funnel steps
FUNNEL_MAP = {
    # Stage 1: Entrance / Awareness
    "entry_camera": "1_Entrance",
    
    # Stage 2: Browsing / Engagement (Aisles and Storage Areas)
    "floor_camera1": "2_Browsing",
    "floor_camera2": "2_Browsing",
    "storage_area": "2_Browsing",
    
    # Stage 3: Checkout / Purchase
    "billing_camera": "3_Checkout"
}

# Standard funnel stages sequence
STAGES_ORDER = ["1_Entrance", "2_Browsing", "3_Checkout"]

# ==============================================================================
# Core Analytical Modules
# ==============================================================================

def reconstruct_customer_sessions(events: List[CCTVEventPayload]) -> Dict[int, Dict[str, Any]]:
    """
    Reconstructs complete shopping session data for each tracking ID.
    Traces spatial transition timelines, total session times, and funnel stages reached.
    """
    if not events:
        return {}
        
    # Group events by track ID and sort chronologically
    events_by_customer = defaultdict(list)
    for event in events:
        events_by_customer[event.track_id].append(event)
        
    sessions = {}
    
    for track_id, cust_events in events_by_customer.items():
        # Sort chronologically
        cust_events.sort(key=lambda x: x.timestamp)
        
        first_event = cust_events[0]
        last_event = cust_events[-1]
        
        # Calculate overall duration
        duration_ms = last_event.timestamp - first_event.timestamp
        duration_sec = duration_ms / 1000.0
        
        # Chronological list of camera zones visited
        camera_sequence = []
        stages_reached = set()
        
        # Build path sequence and record funnel stages
        for event in cust_events:
            camera = event.camera_id
            if not camera_sequence or camera_sequence[-1] != camera:
                camera_sequence.append(camera)
                
            # Map camera to funnel stage
            stage = FUNNEL_MAP.get(camera, "2_Browsing") # Fallback to Browsing if floor-like
            stages_reached.add(stage)
            
        # Top-of-Funnel Safeguard: If customer is detected in browsing/checkout,
        # they implicitly entered the store (Stage 1 is active)
        if "2_Browsing" in stages_reached or "3_Checkout" in stages_reached:
            stages_reached.add("1_Entrance")
        if "3_Checkout" in stages_reached:
            stages_reached.add("2_Browsing")
            
        # Register completed purchase status
        purchased = "3_Checkout" in stages_reached
        
        sessions[track_id] = {
            "track_id": track_id,
            "start_time_ms": first_event.timestamp,
            "end_time_ms": last_event.timestamp,
            "session_duration_sec": round(max(0.0, duration_sec), 2),
            "camera_sequence": camera_sequence,
            "stages_reached": list(stages_reached),
            "last_seen_camera": camera_sequence[-1] if camera_sequence else "N/A",
            "purchased": purchased,
            "abandoned": not purchased
        }
        
    return sessions


def detect_abandoned_journeys(sessions: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filters session profiles to isolate abandoned customer journeys.
    Identifies the drop-off locations to highlight conversion friction points.
    """
    abandoned_records = []
    
    for track_id, session in sessions.items():
        if session["abandoned"]:
            # Gather journey details
            abandoned_records.append({
                "track_id": track_id,
                "session_duration_sec": session["session_duration_sec"],
                "last_seen_camera": session["last_seen_camera"],
                "camera_sequence": session["camera_sequence"],
                "stages_reached": session["stages_reached"]
            })
            
    return abandoned_records


def calculate_funnel_analytics(sessions: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes absolute visitor tallies and percentage conversions across funnel stages.
    """
    total_sessions = len(sessions)
    if total_sessions == 0:
        return {
            "funnel_counts": {s: 0 for s in STAGES_ORDER},
            "conversion_rates": {
                "entrance_to_browse_pct": 0.0,
                "entrance_to_checkout_pct": 0.0,
                "browse_to_checkout_pct": 0.0
            }
        }
        
    # Count unique visitors at each stage
    stage_counts = {stage: 0 for stage in STAGES_ORDER}
    
    for session in sessions.values():
        for stage in session["stages_reached"]:
            if stage in stage_counts:
                stage_counts[stage] += 1
                
    # Calculate conversion percentages
    ent_count = stage_counts["1_Entrance"]
    brw_count = stage_counts["2_Browsing"]
    chk_count = stage_counts["3_Checkout"]
    
    brw_rate = (brw_count / ent_count * 100.0) if ent_count > 0 else 0.0
    chk_rate = (chk_count / ent_count * 100.0) if ent_count > 0 else 0.0
    eff_rate = (chk_count / brw_count * 100.0) if brw_count > 0 else 0.0
    
    return {
        "funnel_counts": stage_counts,
        "conversion_rates": {
            "entrance_to_browse_pct": round(brw_rate, 1),
            "entrance_to_checkout_pct": round(chk_rate, 1),  # Total Conversion
            "browse_to_checkout_pct": round(eff_rate, 1)    # Consideration Efficiency
        }
    }


def generate_session_summaries(sessions: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregates session parameters to compare completed vs. abandoned lifecycles.
    """
    total = len(sessions)
    if total == 0:
        return {
            "total_sessions": 0,
            "completed_purchases": 0,
            "abandoned_journeys": 0,
            "average_completed_duration_sec": 0.0,
            "average_abandoned_duration_sec": 0.0,
            "abandonment_by_camera": {}
        }
        
    completed_times = []
    abandoned_times = []
    
    # Map camera -> number of times it was the last seen location of an abandoned journey
    abandonment_cameras = defaultdict(int)
    
    for session in sessions.values():
        duration = session["session_duration_sec"]
        if session["purchased"]:
            completed_times.append(duration)
        else:
            abandoned_times.append(duration)
            abandonment_cameras[session["last_seen_camera"]] += 1
            
    avg_comp = sum(completed_times) / len(completed_times) if completed_times else 0.0
    avg_aban = sum(abandoned_times) / len(abandoned_times) if abandoned_times else 0.0
    
    return {
        "total_sessions": total,
        "completed_purchases": len(completed_times),
        "abandoned_journeys": len(abandoned_times),
        "average_completed_duration_sec": round(avg_comp, 1),
        "average_abandoned_duration_sec": round(avg_aban, 1),
        "abandonment_by_camera": dict(abandonment_cameras)
    }


# ==============================================================================
# Master Dashboard Interface
# ==============================================================================
def compile_funnel_dashboard(events: List[CCTVEventPayload]) -> Dict[str, Any]:
    """
    Aggregates modular session and funnel functions into a single structured
    payload for backend serving and dashboard plots.
    """
    logger.info("Initializing comprehensive funnel analysis computations...")
    
    # Reconstruct sessions
    sessions = reconstruct_customer_sessions(events)
    
    # Compute conversion rates
    funnel_metrics = calculate_funnel_analytics(sessions)
    
    # Compute session aggregates
    session_summary = generate_session_summaries(sessions)
    
    # Detect abandoned details
    abandoned_details = detect_abandoned_journeys(sessions)
    
    dashboard_payload = {
        "funnel": funnel_metrics,
        "summary": session_summary,
        "abandoned_customer_samples": abandoned_details[:10]  # Limit sample records to 10
    }
    
    logger.info(
        f"Funnel computation complete | "
        f"Sessions: {session_summary['total_sessions']} | "
        f"Conversion: {funnel_metrics['conversion_rates']['entrance_to_checkout_pct']}%"
    )
    return dashboard_payload
