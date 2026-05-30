#!/usr/bin/env python3
"""
FastAPI Central REST API Gateway
Purplle Store Intelligence Challenge

This module provides a unified, production-ready API interface for the Store Intelligence
CCTV analytics platform. It mounts modular sub-routers, provides telemetry ingestion,
serves aggregated store metrics, and triggers real-time anomaly alerts.
"""

import os
import sys
import logging
from typing import Dict, List, Any
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

# Setup import paths to allow executing this file directly
try:
    from app.ingestion import store, ingest_json_file, ingest_batch_payload
    from app.models import CCTVBatchEvents
    from app.metrics import compile_dashboard_summary, get_active_visitors
    from app.funnel import compile_funnel_dashboard
    from app.anomalies import analyze_store_anomalies
    from app.health import router as health_router
except ImportError:
    try:
        from ingestion import store, ingest_json_file, ingest_batch_payload
        from models import CCTVBatchEvents
        from metrics import compile_dashboard_summary, get_active_visitors
        from funnel import compile_funnel_dashboard
        from anomalies import analyze_store_anomalies
        from health import router as health_router
    except ImportError:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from ingestion import store, ingest_json_file, ingest_batch_payload
        from models import CCTVBatchEvents
        from metrics import compile_dashboard_summary, get_active_visitors
        from funnel import compile_funnel_dashboard
        from anomalies import analyze_store_anomalies
        from health import router as health_router

# ==============================================================================
# Logging Configuration
# ==============================================================================
def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a standardized logger for the central API.
    """
    logger = logging.getLogger("CCTV_API")
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
# API Application Initialization
# ==============================================================================
app = FastAPI(
    title="Purplle Store Intelligence API",
    version="1.0.0",
    description=(
        "Production-ready REST API gateway serving CCTV customer detection, "
        "ByteTrack tracking coordinates, dwell times, funnel conversions, and retail anomalies."
    ),
    docs_url="/docs",     # Swagger UI
    redoc_url="/redoc"    # ReDoc
)

# Configure Cross-Origin Resource Sharing (CORS)
# Enables local connection mappings with Streamlit web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow standard dev cross-origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# Router Integrations
# ==============================================================================
# Mount the modular health check and video pipeline status diagnostics router
app.include_router(health_router)

# ==============================================================================
# Startup Event: Automated Telemetry Ingestion Restore
# ==============================================================================
@app.on_event("startup")
def startup_telemetry_restore():
    """
    On API boot, automatically scans the data/events/ folder to auto-ingest
    any pre-existing tracking telemetry, restoring system state immediately.
    """
    logger.info("API Server starting up. Scanning for existing telemetry log archives...")
    event_dir = "data/events"
    
    if os.path.exists(event_dir):
        total_ingested = 0
        for file_name in os.listdir(event_dir):
            # Ingest only valid pipeline output JSON files, skipping test outputs
            if file_name.endswith(".json") and file_name != "test_events.json":
                full_path = os.path.join(event_dir, file_name)
                try:
                    ingested_count = ingest_json_file(full_path)
                    total_ingested += ingested_count
                    if ingested_count > 0:
                        logger.info(f"Auto-ingested {ingested_count} events from target log: '{file_name}'")
                except Exception as e:
                    logger.error(f"Failed to auto-ingest '{file_name}'. Error: {e}")
                    
        logger.info(f"State restoration complete. Pre-loaded {total_ingested} event logs into memory.")
    else:
        logger.info("No events archive directory found. Cache starts empty.")

# ==============================================================================
# Telemetry Ingestion Endpoint
# ==============================================================================
@app.post(
    "/api/ingest",
    status_code=status.HTTP_201_CREATED,
    summary="Batch Telemetry Ingestion",
    description="Allows CCTV pipelines to uplink batches of validated coordinate telemetry events directly to memory cache."
)
async def ingest_telemetry_payload(payload: CCTVBatchEvents) -> Dict[str, Any]:
    """
    Receives and processes uploaded CCTV customer tracking logs.
    """
    logger.info(f"Ingestion Request received with {len(payload.events)} telemetry events.")
    try:
        inserted = ingest_batch_payload(payload)
        return {
            "status": "success",
            "message": f"Successfully validated and ingested {inserted} events.",
            "total_cached_events": store.count
        }
    except Exception as e:
        logger.error(f"In-memory batch ingestion failed. Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Telemetry ingestion failed: {str(e)}"
        )

# ==============================================================================
# Analytics & Reports Endpoint Gateway
# ==============================================================================

@app.get(
    "/api/analytics/summary",
    summary="Dashboard KPIs & Traffic Aggregates",
    description="Computes and compiles store people counts, live occupancy, busiest camera zones, and traffic charts."
)
async def get_analytics_summary() -> Dict[str, Any]:
    """
    Exposes unified store KPIs compiled from active in-memory events.
    """
    events = store.get_all_events()
    if not events:
        return {
            "status": "empty",
            "message": "In-memory database is empty. No telemetry has been ingested yet.",
            "kpis": {
                "total_unique_customers": 0,
                "active_occupancy": 0,
                "average_dwell_time_sec": 0.0,
                "median_dwell_time_sec": 0.0,
                "busiest_camera_zone": "N/A"
            }
        }
    try:
        summary = compile_dashboard_summary(events)
        return summary
    except Exception as e:
        logger.error(f"Failed to compile analytics summary. Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"KPI computation failed: {str(e)}"
        )


@app.get(
    "/api/analytics/funnel",
    summary="Retail Stage Conversion & Session Summaries",
    description="Resolves visitor transits between zones and builds store awareness, consideration, and purchase funnels."
)
async def get_funnel_analytics() -> Dict[str, Any]:
    """
    Exposes conversion funnel rates and customer dropout/abandonment profiles.
    """
    events = store.get_all_events()
    if not events:
        return {
            "status": "empty",
            "message": "In-memory database is empty.",
            "funnel": {
                "funnel_counts": {"1_Entrance": 0, "2_Browsing": 0, "3_Checkout": 0},
                "conversion_rates": {"entrance_to_checkout_pct": 0.0}
            }
        }
    try:
        funnel_dashboard = compile_funnel_dashboard(events)
        return funnel_dashboard
    except Exception as e:
        logger.error(f"Failed to calculate funnel conversions. Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Funnel calculation failed: {str(e)}"
        )


@app.get(
    "/api/analytics/active",
    summary="Retrieve Active In-Store Visitors",
    description="Exposes the track IDs and count of customers currently active on the store floor."
)
async def get_active_store_visitors() -> Dict[str, Any]:
    """
    Exposes list and count of active customers.
    """
    events = store.get_all_events()
    try:
        active_ids = get_active_visitors(events)
        return {
            "active_count": len(active_ids),
            "active_customer_track_ids": active_ids,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        logger.error(f"Failed to extract active visitors. Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Active count retrieval failed: {str(e)}"
        )


@app.get(
    "/api/analytics/anomalies",
    summary="Rule-based Security & Traffic Anomalies",
    description="Processes trajectories against rules to output loitering, velocity spikes, restricted access, or overcrowding alerts."
)
async def get_store_anomalies() -> List[Dict[str, Any]]:
    """
    Exposes detected anomalies validated against AnomalyNotification schema rules.
    """
    events = store.get_all_events()
    if not events:
        return []
    try:
        alerts = analyze_store_anomalies(events)
        # Serialize Pydantic objects to dicts for output
        return [alert.model_dump() for alert in alerts]
    except Exception as e:
        logger.error(f"Failed to execute anomaly detection. Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Anomaly scan failed: {str(e)}"
        )
