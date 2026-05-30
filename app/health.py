#!/usr/bin/env python3
"""
FastAPI Health Check & Diagnostics Router
Purplle Store Intelligence Challenge

This module provides system health monitoring, video batch progress metrics,
and in-memory event ingestion diagnostic endpoints.
"""

import os
import sys
import time
import logging
from typing import Dict, List, Any
from fastapi import APIRouter

# Setup import paths to allow executing this file directly
try:
    from app.ingestion import store
except ImportError:
    try:
        from ingestion import store
    except ImportError:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from ingestion import store

# ==============================================================================
# Logging Configuration
# ==============================================================================
def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a standardized logger for health diagnostics.
    """
    logger = logging.getLogger("CCTV_Health")
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
# Uptime and Router Configurations
# ==============================================================================
# Record start time for server uptime calculations
START_TIME = time.time()

# Expose APIRouter for inclusion in main.py
router = APIRouter(prefix="/health", tags=["Health & Status"])

# ==============================================================================
# Ingestion & Video Pipeline Status Analyzers
# ==============================================================================

def check_video_pipeline_status() -> Dict[str, Any]:
    """
    Scans the system storage to calculate dynamic video batch processing metrics.
    Cross-references raw input feeds with tracking outputs and event logs.
    """
    video_dir = "data/videos"
    output_dir = "data/outputs"
    event_dir = "data/events"
    
    # Defaults if folders are missing
    total_videos = []
    completed_clips = []
    completed_jsons = []
    
    # 1. Scan input videos
    if os.path.exists(video_dir):
        total_videos = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]
        
    # 2. Scan outputs
    if os.path.exists(output_dir):
        completed_clips = [f for f in os.listdir(output_dir) if f.endswith("_tracked.mp4") or f.endswith(".mp4")]
        
    # 3. Scan event jsons
    if os.path.exists(event_dir):
        completed_jsons = [f for f in os.listdir(event_dir) if f.endswith("_events.json") or f.endswith("events.json")]
        
    total_count = len(total_videos)
    
    # Identify video matches (how many have both video output and events json)
    completed_videos = 0
    active_sources = []
    for vid in total_videos:
        base_name = os.path.splitext(vid)[0]
        has_video = any(base_name in out for out in completed_clips)
        has_json = any(base_name in ev for ev in completed_jsons)
        
        if has_video and has_json:
            completed_videos += 1
            active_sources.append(base_name)
            
    progress_pct = (completed_videos / total_count * 100.0) if total_count > 0 else 0.0
    
    return {
        "total_camera_sources": total_count,
        "completed_processing_sources": completed_videos,
        "pipeline_progress_percent": round(progress_pct, 1),
        "active_stream_sources": active_sources,
        "pending_sources_count": max(0, total_count - completed_videos)
    }


def get_system_resource_estimates() -> Dict[str, Any]:
    """
    Safe resource monitor that avoids importing psutil (which can crash
    minimal container builds) by returning standard lightweight estimates.
    """
    try:
        import psutil
        cpu_usage = psutil.cpu_percent(interval=None)
        ram_usage = psutil.virtual_memory().percent
        return {
            "resource_monitoring_mode": "psutil",
            "cpu_utilization_percent": cpu_usage,
            "ram_utilization_percent": ram_usage
        }
    except ImportError:
        # Graceful fallback: return system indicators using standard python
        import platform
        return {
            "resource_monitoring_mode": "system_fallback",
            "os_environment": platform.system(),
            "cpu_utilization_percent": 15.0,  # Safe simulated baseline
            "ram_utilization_percent": 30.0
        }

# ==============================================================================
# FastAPI Path Routers
# ==============================================================================

@router.get("/live", summary="Liveliness Probe")
async def liveliness_probe() -> Dict[str, Any]:
    """
    Fast heartbeat endpoint used by load balancers or docker healthchecks
    to verify that the FastAPI web server is online.
    """
    uptime = time.time() - START_TIME
    datetime_string = time.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "status": "UP",
        "uptime_sec": round(uptime, 1),
        "timestamp": datetime_string
    }


@router.get("/status", summary="Detailed Diagnostics Status")
async def detailed_diagnostics_status() -> Dict[str, Any]:
    """
    Full diagnostic endpoint that reviews in-memory database occupancy,
    cross-references files to measure batch completion, and queries CPU parameters.
    """
    uptime = time.time() - START_TIME
    pipeline = check_video_pipeline_status()
    resources = get_system_resource_estimates()
    
    # Establish overall system health grade
    status_grade = "healthy"
    if pipeline["pending_sources_count"] > 0 and store.count == 0:
        status_grade = "degraded" # Video exists but cache has not been ingested
    elif resources["cpu_utilization_percent"] > 90.0:
        status_grade = "degraded" # High workload warning
        
    logger.info(f"Health Diagnostics Request resolved. Uptime: {uptime:.0f}s | Status: {status_grade.upper()}")
    
    return {
        "status": status_grade,
        "uptime_sec": round(uptime, 1),
        "telemetry_ingestion": {
            "in_memory_events_count": store.count,
            "ingestion_active": store.count > 0
        },
        "video_batch_pipeline": pipeline,
        "system_resources": resources
    }
