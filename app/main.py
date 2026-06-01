#!/usr/bin/env python3
"""
FastAPI Central REST API Gateway
Purplle Store Intelligence Challenge
UPGRADED: Real-time + Unique Identity Tracking + Streaming System
"""

import os
import sys
import logging
import time
import asyncio
from typing import Dict, List, Any
from collections import defaultdict

from fastapi import FastAPI, HTTPException, status, WebSocket
from fastapi.middleware.cors import CORSMiddleware

# ==============================================================================
# SAFE IMPORTS
# ==============================================================================
try:
    from app.ingestion import store, ingest_json_file, ingest_batch_payload
    from app.models import CCTVBatchEvents
    from app.metrics import compile_dashboard_summary, get_active_visitors
    from app.funnel import compile_funnel_dashboard
    from app.anomalies import analyze_store_anomalies
    from app.health import router as health_router
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

    from ingestion import store, ingest_json_file, ingest_batch_payload
    from models import CCTVBatchEvents
    from metrics import compile_dashboard_summary, get_active_visitors
    from funnel import compile_funnel_dashboard
    from anomalies import analyze_store_anomalies
    from health import router as health_router


# ==============================================================================
# LOGGER
# ==============================================================================
def setup_logger():
    logger = logging.getLogger("CCTV_API")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger()


# ==============================================================================
# FASTAPI APP
# ==============================================================================
app = FastAPI(
    title="Purplle Store Intelligence API",
    version="2.0.0",
    description="Production Real-time CCTV Analytics System"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)


# ==============================================================================
# GLOBAL REAL-TIME STATE (FIX DUPLICATE COUNTING)
# ==============================================================================
seen_track_ids = set()
active_tracks = defaultdict(int)


def register_unique_visitors(events):
    """
    FIX: Ensures same person is counted only ONCE using track_id.
    """
    global seen_track_ids, active_tracks

    seen_track_ids.clear()
    active_tracks.clear()

    for e in events:
        track_id = getattr(e, "track_id", None)

        if track_id is None:
            continue

        seen_track_ids.add(track_id)
        active_tracks[track_id] += 1

    return list(seen_track_ids)


# ==============================================================================
# STARTUP LOAD EVENTS
# ==============================================================================
@app.on_event("startup")
def startup_load():
    logger.info("Loading stored CCTV events...")

    event_dir = "data/events"
    total = 0

    if os.path.exists(event_dir):
        for f in os.listdir(event_dir):
            if f.endswith(".json"):
                total += ingest_json_file(os.path.join(event_dir, f))

    logger.info(f"Loaded {total} events into memory")


# ==============================================================================
# MANUAL RELOAD (IMPORTANT FIX)
# ==============================================================================
@app.get("/api/reload-events")
def reload_events():
    event_dir = "data/events"
    total = 0

    if os.path.exists(event_dir):
        for f in os.listdir(event_dir):
            if f.endswith(".json"):
                total += ingest_json_file(os.path.join(event_dir, f))

    return {
        "status": "reloaded",
        "events_loaded": total,
        "total_in_memory": store.count
    }


# ==============================================================================
# INGESTION
# ==============================================================================
@app.post("/api/ingest")
async def ingest(payload: CCTVBatchEvents):
    try:
        inserted = ingest_batch_payload(payload)
        return {
            "status": "success",
            "inserted": inserted,
            "total": store.count
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ==============================================================================
# ANALYTICS - SUMMARY
# ==============================================================================
@app.get("/api/analytics/summary")
def summary():
    events = store.get_all_events()

    if not events:
        return {"status": "empty"}

    return compile_dashboard_summary(events)


# ==============================================================================
# ANALYTICS - FUNNEL
# ==============================================================================
@app.get("/api/analytics/funnel")
def funnel():
    events = store.get_all_events()

    if not events:
        return {"status": "empty"}

    return compile_funnel_dashboard(events)


# ==============================================================================
# ANALYTICS - ACTIVE USERS (FIXED DUPLICATES)
# ==============================================================================
@app.get("/api/analytics/active")
def active_users():
    events = store.get_all_events()

    unique_ids = register_unique_visitors(events)

    return {
        "active_count": len(unique_ids),
        "unique_visitors": len(seen_track_ids),
        "active_ids": unique_ids,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }


# ==============================================================================
# ANALYTICS - ANOMALIES
# ==============================================================================
@app.get("/api/analytics/anomalies")
def anomalies():
    events = store.get_all_events()

    if not events:
        return []

    alerts = analyze_store_anomalies(events)
    return [a.model_dump() for a in alerts]


# ==============================================================================
# REAL-TIME WEBSOCKET STREAM (CORE FEATURE)
# ==============================================================================
@app.websocket("/ws/live")
async def live_stream(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            events = store.get_all_events()

            unique_ids = register_unique_visitors(events)

            payload = {
                "active_count": len(unique_ids),
                "total_events": len(events),
                "unique_visitors": len(seen_track_ids),
                "timestamp": time.strftime("%H:%M:%S")
            }

            await websocket.send_json(payload)

            # real-time update interval
            await asyncio.sleep(1)

    except Exception:
        logger.info("WebSocket disconnected")
@app.get("/ping")
def ping():
    return {"status": "alive"}