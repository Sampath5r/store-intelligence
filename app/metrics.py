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

    event_priority = {"enter": 0, "update": 1, "exit": 2}

    # Group events by track ID and find the chronologically latest event for each
    latest_event_by_track: Dict[int, CCTVEventPayload] = {}
    for event in events:
        track_id = event.track_id
        if track_id not in latest_event_by_track:
            latest_event_by_track[track_id] = event
        else:
            current_latest = latest_event_by_track[track_id]
            is_newer = event.timestamp > current_latest.timestamp
            is_same_time_with_final_state = (
                event.timestamp == current_latest.timestamp
                and event_priority.get(event.event_type, 0) >= event_priority.get(current_latest.event_type, 0)
            )
            if is_newer or is_same_time_with_final_state:
                latest_event_by_track[track_id] = event

    active_tracks = []
    for track_id, last_event in latest_event_by_track.items():
        if last_event.event_type != "exit":
            active_tracks.append(track_id)

    return active_tracks


def group_events_by_track(events: List[CCTVEventPayload]) -> Dict[int, List[CCTVEventPayload]]:
    """
    Groups telemetry by tracking ID and sorts each customer's events chronologically.
    """
    grouped_events: Dict[int, List[CCTVEventPayload]] = defaultdict(list)
    for event in events:
        grouped_events[event.track_id].append(event)

    for track_events in grouped_events.values():
        track_events.sort(key=lambda e: e.timestamp)

    return dict(grouped_events)


def group_events_by_zone_and_track(
    events: List[CCTVEventPayload],
) -> Dict[str, Dict[int, List[CCTVEventPayload]]]:
    """
    Groups telemetry by camera zone, then track ID, keeping each track sorted.
    """
    grouped: Dict[str, Dict[int, List[CCTVEventPayload]]] = defaultdict(lambda: defaultdict(list))
    for event in events:
        grouped[event.camera_id][event.track_id].append(event)

    sorted_grouped: Dict[str, Dict[int, List[CCTVEventPayload]]] = {}
    for camera_id, tracks in grouped.items():
        sorted_grouped[camera_id] = {}
        for track_id, track_events in tracks.items():
            sorted_grouped[camera_id][track_id] = sorted(track_events, key=lambda e: e.timestamp)

    return sorted_grouped


def _event_span_dwell_sec(track_events: List[CCTVEventPayload]) -> float:
    """
    Calculates observed dwell duration from first to last event timestamp.
    """
    if not track_events:
        return 0.0

    first_seen = track_events[0].timestamp
    last_seen = track_events[-1].timestamp
    return max(0.0, (last_seen - first_seen) / 1000.0)


def _explicit_exit_dwell_sec(track_events: List[CCTVEventPayload]) -> float:
    """
    Sums explicit dwell durations emitted on exit events, when available.
    """
    dwell_values = [
        float(event.dwell_time_sec)
        for event in track_events
        if event.event_type == "exit" and event.dwell_time_sec is not None
    ]
    return max(0.0, float(sum(dwell_values)))


def _track_dwell_sec(track_events: List[CCTVEventPayload]) -> float:
    """
    Prefers event-emitter dwell values, then falls back to observed timestamp span.
    """
    explicit_dwell = _explicit_exit_dwell_sec(track_events)
    if explicit_dwell > 0.0:
        return explicit_dwell
    return _event_span_dwell_sec(track_events)


def calculate_customer_dwell_times(events: List[CCTVEventPayload]) -> List[Dict[str, Any]]:
    """
    Calculates dwell duration and zone context for every tracked customer ID.
    """
    if not events:
        return []

    logger.info("Calculating per-customer dwell durations from %d telemetry events.", len(events))
    grouped_events = group_events_by_track(events)
    dwell_rows: List[Dict[str, Any]] = []

    for track_id, track_events in grouped_events.items():
        first_event = track_events[0]
        last_event = track_events[-1]
        zones_visited = []

        for event in track_events:
            if event.camera_id not in zones_visited:
                zones_visited.append(event.camera_id)

        total_dwell_sec = _track_dwell_sec(track_events)
        dwell_rows.append({
            "track_id": track_id,
            "total_dwell_time_sec": round(total_dwell_sec, 2),
            "first_seen_ms": round(float(first_event.timestamp), 2),
            "last_seen_ms": round(float(last_event.timestamp), 2),
            "event_count": len(track_events),
            "zones_visited": zones_visited,
            "last_camera_id": last_event.camera_id,
            "is_active": last_event.event_type != "exit"
        })

    dwell_rows.sort(key=lambda row: row["total_dwell_time_sec"], reverse=True)
    logger.info("Computed dwell durations for %d customer track ID(s).", len(dwell_rows))
    return dwell_rows


def calculate_zone_dwell_analytics(events: List[CCTVEventPayload]) -> List[Dict[str, Any]]:
    """
    Computes dwell and engagement statistics for each camera zone.
    """
    if not events:
        return []

    zone_tracks = group_events_by_zone_and_track(events)
    zone_rows: List[Dict[str, Any]] = []

    for camera_id, tracks in zone_tracks.items():
        dwell_times = [_track_dwell_sec(track_events) for track_events in tracks.values()]
        dwell_times = [dwell for dwell in dwell_times if dwell >= 0.0]
        dwell_array = np.array(dwell_times, dtype=np.float32) if dwell_times else np.array([], dtype=np.float32)
        total_events = sum(len(track_events) for track_events in tracks.values())
        unique_customers = len(tracks)
        total_dwell_sec = float(np.sum(dwell_array)) if dwell_array.size else 0.0
        average_dwell_sec = float(np.mean(dwell_array)) if dwell_array.size else 0.0
        median_dwell_sec = float(np.median(dwell_array)) if dwell_array.size else 0.0

        # The engagement score favors zones where many customers spend meaningful time.
        engagement_score = total_dwell_sec * max(1, unique_customers)
        zone_rows.append({
            "camera_id": camera_id,
            "unique_customers": unique_customers,
            "total_events": total_events,
            "total_dwell_time_sec": round(total_dwell_sec, 2),
            "average_dwell_time_sec": round(average_dwell_sec, 2),
            "median_dwell_time_sec": round(median_dwell_sec, 2),
            "engagement_score": round(engagement_score, 2)
        })

    zone_rows.sort(
        key=lambda row: (
            row["engagement_score"],
            row["total_dwell_time_sec"],
            row["unique_customers"],
            row["total_events"]
        ),
        reverse=True,
    )
    logger.info("Computed dwell engagement analytics for %d camera zone(s).", len(zone_rows))
    return zone_rows


def detect_high_engagement_zones(
    events: List[CCTVEventPayload],
    top_n: int = 3,
    zone_analytics: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Returns top camera zones ranked by dwell-heavy engagement.
    """
    zone_rows = zone_analytics if zone_analytics is not None else calculate_zone_dwell_analytics(events)
    if not zone_rows:
        return []

    average_score = float(np.mean([row["engagement_score"] for row in zone_rows]))
    high_engagement = []

    for rank, row in enumerate(zone_rows[:max(1, top_n)], start=1):
        annotated = dict(row)
        annotated["rank"] = rank
        annotated["is_high_engagement"] = row["engagement_score"] >= average_score
        high_engagement.append(annotated)

    logger.info("Detected %d high-engagement zone candidate(s).", len(high_engagement))
    return high_engagement


def calculate_dwell_analytics(events: List[CCTVEventPayload]) -> Dict[str, Any]:
    """
    Computes dwell-time metrics, per-track durations, and zone engagement summary.
    """
    if not events:
        return {
            "average_dwell_time_sec": 0.0,
            "median_dwell_time_sec": 0.0,
            "total_customers_measured": 0,
            "longest_dwell_track_id": None,
            "dwell_time_distribution": {},
            "customer_dwell_times": [],
            "zone_engagement": [],
            "high_engagement_zones": []
        }

    customer_dwell_times = calculate_customer_dwell_times(events)
    zone_engagement = calculate_zone_dwell_analytics(events)
    high_engagement_zones = detect_high_engagement_zones(events, zone_analytics=zone_engagement)
    dwell_times = [row["total_dwell_time_sec"] for row in customer_dwell_times]

    if not dwell_times:
        return {
            "average_dwell_time_sec": 0.0,
            "median_dwell_time_sec": 0.0,
            "total_customers_measured": 0,
            "longest_dwell_track_id": None,
            "dwell_time_distribution": {},
            "customer_dwell_times": [],
            "zone_engagement": zone_engagement,
            "high_engagement_zones": high_engagement_zones
        }

    # Calculate statistical metrics
    dwell_array = np.array(dwell_times, dtype=np.float32)
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

    longest_dwell = customer_dwell_times[0] if customer_dwell_times else None

    return {
        "average_dwell_time_sec": round(avg_dwell, 2),
        "median_dwell_time_sec": round(median_dwell, 2),
        "total_customers_measured": len(dwell_times),
        "longest_dwell_track_id": longest_dwell["track_id"] if longest_dwell else None,
        "longest_dwell_time_sec": longest_dwell["total_dwell_time_sec"] if longest_dwell else 0.0,
        "dwell_time_distribution": distribution,
        "customer_dwell_times": customer_dwell_times,
        "zone_engagement": zone_engagement,
        "high_engagement_zones": high_engagement_zones
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


def get_camera_traffic_breakdown(
    events: List[CCTVEventPayload],
    zone_engagement: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
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
        
    zone_dwell_lookup = {
        row["camera_id"]: row
        for row in (zone_engagement if zone_engagement is not None else calculate_zone_dwell_analytics(events))
    }

    breakdown = []
    for camera in camera_events.keys():
        unique_visitors = len(camera_visitors[camera])
        total_signals = camera_events[camera]
        dwell_row = zone_dwell_lookup.get(camera, {})
        breakdown.append({
            "camera_id": camera,
            "unique_visitors": unique_visitors,
            "total_detections": total_signals,
            "signals_per_visitor": round(total_signals / unique_visitors, 1) if unique_visitors > 0 else 0,
            "average_dwell_time_sec": dwell_row.get("average_dwell_time_sec", 0.0),
            "total_dwell_time_sec": dwell_row.get("total_dwell_time_sec", 0.0),
            "engagement_score": dwell_row.get("engagement_score", 0.0)
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
    camera_breakdown = get_camera_traffic_breakdown(
        events,
        zone_engagement=dwell_stats["zone_engagement"]
    )
    
    # Identify busiest camera
    busiest_cam = camera_breakdown[0]["camera_id"] if camera_breakdown else "N/A"
    highest_engagement_zone = (
        dwell_stats["high_engagement_zones"][0]["camera_id"]
        if dwell_stats["high_engagement_zones"]
        else "N/A"
    )
    
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
            "longest_dwell_track_id": dwell_stats["longest_dwell_track_id"],
            "longest_dwell_time_sec": dwell_stats.get("longest_dwell_time_sec", 0.0),
            "busiest_camera_zone": busiest_cam,
            "highest_engagement_zone": highest_engagement_zone,
            "peak_traffic_count": peak_visitor_count,
            "peak_traffic_period": peak_time_readable
        },
        "dwell_analytics": {
            "average_dwell_time_sec": dwell_stats["average_dwell_time_sec"],
            "median_dwell_time_sec": dwell_stats["median_dwell_time_sec"],
            "total_customers_measured": dwell_stats["total_customers_measured"],
            "longest_dwell_track_id": dwell_stats["longest_dwell_track_id"],
            "longest_dwell_time_sec": dwell_stats.get("longest_dwell_time_sec", 0.0)
        },
        "customer_dwell_times": dwell_stats["customer_dwell_times"],
        "zone_engagement": dwell_stats["zone_engagement"],
        "high_engagement_zones": dwell_stats["high_engagement_zones"],
        "dwell_distribution": dwell_stats["dwell_time_distribution"],
        "traffic_timeline": traffic_periods,
        "camera_rankings": camera_breakdown
    }
    
    logger.info("Batch metrics compilation complete.")
    return summary
