#!/usr/bin/env python3
"""
Pydantic Data Models & Schemas
Purplle Store Intelligence Challenge

This module contains centralized Pydantic models for the FastAPI backend,
enforcing strict validation for video telemetry payloads and structuring
standard response schemas for the retail analytics dashboard.
"""

from typing import List, Dict, Optional, Any, Tuple
from pydantic import BaseModel, Field, field_validator, confloat, conint
from datetime import datetime

# ==============================================================================
# 1. Telemetry Ingestion Schemas
# ==============================================================================
class CCTVEventPayload(BaseModel):
    """
    Enforces strict validation on spatial telemetry events posted from tracking cameras.
    """
    timestamp: float = Field(
        ..., 
        description="Relative video timestamp in milliseconds from stream start.",
        example=12500.0
    )
    camera_id: str = Field(
        ..., 
        description="Identifier of the CCTV camera source (e.g. entry_camera, billing_camera).",
        example="entry_camera"
    )
    track_id: conint(ge=0) = Field(
        ..., 
        description="Persistent tracking ID assigned to the customer.",
        example=42
    )
    bbox: List[int] = Field(
        ..., 
        description="Bounding box coordinates [x1, y1, x2, y2] in pixels.",
        example=[120, 240, 210, 480]
    )
    confidence: confloat(ge=0.0, le=1.0) = Field(
        ..., 
        description="Detection confidence rating from YOLOv8 (0.0 to 1.0).",
        example=0.89
    )
    event_type: str = Field(
        ..., 
        description="Type of telemetry event. Must be: 'enter', 'exit', or 'update'.",
        example="enter"
    )
    dwell_time_sec: Optional[float] = Field(
        default=None, 
        description="Dwell duration in seconds. Appended only on 'exit' event types.",
        example=15.4
    )

    @field_validator('bbox')
    @classmethod
    def validate_bbox_format(cls, value: List[int]) -> List[int]:
        """
        Validates that bounding boxes contain exactly 4 spatial coordinates
        representing a positive, logical bounding area.
        """
        if len(value) != 4:
            raise ValueError("Bounding box must contain exactly 4 integers [x1, y1, x2, y2].")
        x1, y1, x2, y2 = value
        if x1 > x2 or y1 > y2:
            raise ValueError("Bounding box coordinates must be logical: x1 <= x2 and y1 <= y2.")
        return value

    @field_validator('event_type')
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        """
        Restricts event type field to allowed categories.
        """
        allowed = {"enter", "exit", "update"}
        normalized = value.strip().lower()
        if normalized not in allowed:
            raise ValueError(f"Invalid event_type. Allowed types: {allowed}")
        return normalized


class CCTVBatchEvents(BaseModel):
    """
    Enables low-overhead batch upload requests of compiled frame telemetry.
    """
    events: List[CCTVEventPayload] = Field(
        ..., 
        description="List of CCTV spatial telemetry events."
    )


# ==============================================================================
# 2. Analytics Reporting Schemas
# ==============================================================================
class DwellTimeSummary(BaseModel):
    """
    Structures dwell-time statistics and distributions for retail reporting.
    """
    average_dwell_time_sec: float = Field(..., description="Average stay duration of customers in seconds.")
    median_dwell_time_sec: float = Field(..., description="Median stay duration of customers in seconds.")
    total_customers_measured: int = Field(..., description="Total visitors included in calculations.")
    dwell_time_distribution: Dict[str, int] = Field(
        ..., 
        description="Map of dwell-time range buckets to visitor counts.",
        example={"< 30s": 15, "30s-2m": 35, "2m-5m": 50, "> 5m": 8}
    )


class TrafficMetrics(BaseModel):
    """
    Summarizes overall spatial entry/exit rates and current live occupancy.
    """
    camera_id: str = Field(..., description="Camera ID zone being analyzed.")
    total_entries: int = Field(..., description="Total entries registered in the zone.")
    total_exits: int = Field(..., description="Total exits registered in the zone.")
    current_occupancy: int = Field(..., description="Estimate of currently active customers in the zone.")
    hourly_traffic: Dict[str, int] = Field(
        ..., 
        description="Traffic frequency mapped by hourly periods.",
        example={"09:00-10:00": 12, "10:00-11:00": 34, "11:00-12:00": 28}
    )


class CustomerJourney(BaseModel):
    """
    Represents the physical journey trajectory of a customer across camera zones.
    """
    track_id: int = Field(..., description="Persistent tracking identifier of the customer.")
    zones_visited: List[str] = Field(..., description="Sequential list of camera zones visited.")
    entry_time: datetime = Field(..., description="First registered timestamp when customer entered the store.")
    exit_time: Optional[datetime] = Field(default=None, description="Timestamp when customer exited the store.")
    total_dwell_time_sec: float = Field(..., description="Total stay duration in seconds.")
    path_sequence: List[Dict[str, Any]] = Field(
        ...,
        description="Granular sequence records of entry, exit, and dwell per zone.",
        example=[
            {"zone": "entry_camera", "entered_at": "10:00:00", "left_at": "10:00:30", "dwell": 30.0},
            {"zone": "floor_camera1", "entered_at": "10:00:35", "left_at": "10:03:00", "dwell": 145.0}
        ]
    )


class FunnelAnalyticsSummary(BaseModel):
    """
    Maps multi-stage retail conversion funnels and calculations.
    """
    total_store_visitors: int = Field(..., description="Total entry counts registered at main entrance.")
    total_browsers: int = Field(..., description="Total customers who progressed to browse floor zones.")
    total_checkouts: int = Field(..., description="Total customer transactions registered in billing area.")
    
    # Conversion ratios (0.0 to 100.0)
    browse_rate_percent: float = Field(..., description="Store visitors who transitioned to browsing.")
    checkout_rate_percent: float = Field(..., description="Store visitors who completed checkout.")
    conversion_efficiency: float = Field(..., description="Browsers who transitioned to checkout.")
    
    stage_progression: Dict[str, int] = Field(
        ...,
        description="Visitor counts at each distinct retail journey stage.",
        example={"1_Entrance": 120, "2_Browsing": 84, "3_Checkout": 32}
    )


# ==============================================================================
# 3. Alerts & Health Schemas
# ==============================================================================
class AnomalyNotification(BaseModel):
    """
    Defines structure for anomalous retail patterns or system security alerts.
    """
    alert_id: str = Field(..., description="Unique generated UUID for the alert.")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="UTC time when anomaly was detected.")
    anomaly_type: str = Field(
        ..., 
        description="Type of anomaly (e.g. unusual_occupancy, cashier_bottleneck, loitering_alert).",
        example="cashier_bottleneck"
    )
    camera_id: str = Field(..., description="CCTV Camera zone where the anomaly was recorded.")
    track_id: Optional[int] = Field(default=None, description="Tracking ID of customer associated with the alert.")
    severity: str = Field(..., description="Urgency classification: 'low', 'medium', or 'high'.", example="medium")
    details: str = Field(..., description="Descriptive context explaining the anomaly details.")


class PipelineHealth(BaseModel):
    """
    Monitors live CCTV ingestion rates, latency, and system server status.
    """
    status: str = Field(..., description="Overall pipeline status: 'healthy', 'degraded', or 'offline'.", example="healthy")
    uptime_seconds: float = Field(..., description="FastAPI server uptime duration.")
    active_cameras_count: int = Field(..., description="Number of currently active camera ingestion streams.")
    average_latency_ms: float = Field(..., description="Average processing lag time per video frame.")
    active_streams: List[str] = Field(..., description="Names of currently connected cameras.")
    system_resource_cpu: float = Field(..., description="CPU utilization percentage.")
