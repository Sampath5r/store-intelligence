#!/usr/bin/env python3
"""
Purplle Store Intelligence - Streamlit Dashboard Client
CCTV Retail Analytics Visualizer

This module serves as the primary visual orchestrator for the retail analytics platform.
It statefully connects to Uvicorn REST APIs (or falls back to scanning local events JSON files)
and coordinates rendering through modular components.
"""

import os
import sys
import requests
import streamlit as st

# Ensure root workspace directory is on sys.path to allow clean imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modular GUI components
from dashboard.components.selectors import render_camera_selector, render_confidence_slider, render_system_status
from dashboard.components.kpi_cards import render_kpi_cards
from dashboard.components.charts import render_funnel_chart, render_dwell_histogram, render_camera_workload
from dashboard.components.heatmap import render_spatial_heatmap
from dashboard.components.anomaly_table import render_anomalies_panel

# Import core analytical fallback functions if API is offline
try:
    from app.ingestion import store as local_store, ingest_json_file
    from app.metrics import compile_dashboard_summary, get_active_visitors
    from app.funnel import compile_funnel_dashboard
    from app.anomalies import analyze_store_anomalies
except ImportError:
    pass

# ==============================================================================
# Page Configuration & Brand Styles
# ==============================================================================
st.set_page_config(
    page_title="Purplle Store Intelligence",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Brand Color Palette Styling
st.markdown("""
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; }
        .stMetric { background-color: #f3e8ff; padding: 12px; border-radius: 8px; border-left: 5px solid #a855f7; }
        .stMetric label { color: #581c87 !important; font-weight: 600; }
        .status-connected { color: #22c55e; font-weight: bold; }
        .status-standalone { color: #3b82f6; font-weight: bold; }
        .status-offline { color: #ef4444; font-weight: bold; }
        h1, h2, h3 { color: #4a044e; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# Dynamic Backend Connection Manager
# ==============================================================================
API_URL = "http://localhost:8000"

def check_api_connection() -> str:
    """
    Validates if the FastAPI server is online.
    Returns 'api', 'standalone', or 'empty'.
    """
    try:
        response = requests.get(f"{API_URL}/health/live", timeout=1)
        if response.status_code == 200:
            return "api"
    except Exception:
        pass
        
    # Check if local logs folder has telemetry to load
    event_dir = "data/events"
    if os.path.exists(event_dir):
        json_files = [f for f in os.listdir(event_dir) if f.endswith(".json") and f != "test_events.json"]
        if json_files:
            return "standalone"
            
    return "empty"

# ==============================================================================
# Local Data Loader & Aggregator Fallback
# ==============================================================================
@st.cache_data(ttl=5) # Cache fallback for 5 seconds to reduce IO load
def fetch_local_fallback_data() -> dict:
    """
    Fallback data loader. Scans data/events/*.json, loads all events in memory,
    and runs local analytical computations to restore dashboard functionality.
    """
    local_store.clear()
    event_dir = "data/events"
    
    if os.path.exists(event_dir):
        for file_name in os.listdir(event_dir):
            if file_name.endswith(".json") and file_name != "test_events.json":
                full_path = os.path.join(event_dir, file_name)
                ingest_json_file(full_path)
                
    events = local_store.get_all_events()
    
    if not events:
        return {}
        
    # Compile analytics locally using modular app engine functions
    summary = compile_dashboard_summary(events)
    funnel = compile_funnel_dashboard(events)
    anomalies = analyze_store_anomalies(events)
    
    return {
        "summary": summary,
        "funnel": funnel,
        "anomalies": [a.model_dump() for a in anomalies],
        "raw_events": events
    }

# ==============================================================================
# API REST Data Ingestion
# ==============================================================================
def fetch_api_data() -> dict:
    """
    Fetches processed analytics datasets directly from the active FastAPI server.
    """
    try:
        summary_resp = requests.get(f"{API_URL}/api/analytics/summary", timeout=2).json()
        funnel_resp = requests.get(f"{API_URL}/api/analytics/funnel", timeout=2).json()
        anomalies_resp = requests.get(f"{API_URL}/api/analytics/anomalies", timeout=2).json()
        
        # Pull raw events via local read if possible for heatmap coordinates plotting
        events = []
        event_dir = "data/events"
        local_store.clear()
        if os.path.exists(event_dir):
            for file_name in os.listdir(event_dir):
                if file_name.endswith(".json") and file_name != "test_events.json":
                    ingest_json_file(os.path.join(event_dir, file_name))
            events = local_store.get_all_events()
            
        return {
            "summary": summary_resp,
            "funnel": funnel_resp,
            "anomalies": anomalies_resp,
            "raw_events": events
        }
    except Exception as e:
        st.error(f"API request failed: {e}. Attempting local logs loading...")
        return {}

# ==============================================================================
# Sidebar Renders & Filters Binding
# ==============================================================================
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/e/e7/Shopping_Bag_Icon.svg", width=80)
st.sidebar.title("Store Intelligence")
st.sidebar.markdown("CCTV Customer Journey Dashboard")
st.sidebar.markdown("---")

# Active connection status check
conn_status = check_api_connection()
render_system_status(conn_status)
st.sidebar.markdown("---")

# Active filters dropdown & slider
camera_list = ["All Cameras", "entry_camera", "billing_camera", "floor_camera1", "floor_camera2", "storage_area"]
selected_camera = render_camera_selector(camera_list)
conf_threshold = render_confidence_slider(default_val=0.25)

st.sidebar.markdown("---")
st.sidebar.info(
    "This platform processes retail CCTV feeds in batch, extracts "
    "persistent track IDs, maps customer journeys, and detects loitering or trespassing."
)

# ==============================================================================
# Data Resolution & Filter Binding
# ==============================================================================
data = {}
if conn_status == "api":
    data = fetch_api_data()
elif conn_status == "standalone":
    data = fetch_local_fallback_data()

# Render warning screen if no files have been processed
if not data or "raw_events" not in data or not data["raw_events"]:
    st.title("🛍️ Purplle Store Intelligence Challenge")
    st.warning(
        "No retail CCTV telemetry detected. Ensure that you have placed CCTV mp4 files in "
        "`data/videos/` and executed the tracking pipeline runner `pipeline/run.sh` to generate event logs."
    )
    st.info("Execute: `bash pipeline/run.sh` to begin tracking.")
    st.stop()

# Filter raw events based on sidebar controls
raw_events = data["raw_events"]
filtered_events = [e for e in raw_events if e.confidence >= conf_threshold]

if selected_camera != "All Cameras":
    filtered_events = [e for e in filtered_events if e.camera_id == selected_camera]
    
# Re-compile metrics dynamically if filter parameters change
if len(filtered_events) != len(raw_events):
    summary_data = compile_dashboard_summary(filtered_events)
    funnel_data = compile_funnel_dashboard(filtered_events)
    anomalies_data = [a.model_dump() for a in analyze_store_anomalies(filtered_events)]
else:
    summary_data = data["summary"]
    funnel_data = data["funnel"]
    anomalies_data = data["anomalies"]

# ==============================================================================
# Layout UI Renders
# ==============================================================================
st.title("🛍️ Purplle Store Intelligence Analytics Dashboard")
st.markdown("Real-Time CCTV Customer Journeys & Spatial Funnel Telemetry")
st.markdown("---")

# Render Reusable KPIs Row
kpi = summary_data.get("kpis", {})
render_kpi_cards(kpi, conn_status)
st.markdown("---")

# Tab Controller layout
tab_funnel, tab_traffic, tab_heatmap, tab_alerts = st.tabs([
    "📈 Retail Conversion Funnel",
    "📊 Dwell & Traffic Metrics",
    "🔥 Spatial Footprint Heatmap",
    "⚠️ Security Anomaly Alerts"
])

# Render modular components into tabs
with tab_funnel:
    render_funnel_chart(funnel_data)

with tab_traffic:
    col_dwell, col_cam = st.columns(2)
    with col_dwell:
        render_dwell_histogram(summary_data.get("dwell_distribution", {}))
    with col_cam:
        render_camera_workload(summary_data.get("camera_rankings", []))

with tab_heatmap:
    render_spatial_heatmap(filtered_events, selected_camera)

with tab_alerts:
    render_anomalies_panel(anomalies_data)
