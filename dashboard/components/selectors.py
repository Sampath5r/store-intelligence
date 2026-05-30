#!/usr/bin/env python3
"""
Dashboard Sidebar Selector Components
Purplle Store Intelligence Challenge
"""

from typing import List
import streamlit as st

def render_camera_selector(camera_list: List[str]) -> str:
    """
    Renders the sidebar dropdown selector to filter metrics by CCTV camera zone.
    """
    return st.sidebar.selectbox(
        "Filter by CCTV Camera:",
        camera_list,
        help="Select a specific CCTV camera source to isolate local metrics and trajectories."
    )


def render_confidence_slider(default_val: float = 0.25) -> float:
    """
    Renders the sidebar slider to filter events by YOLOv8 detection confidence.
    """
    return st.sidebar.slider(
        "Min YOLOv8 Confidence:",
        min_value=0.10,
        max_value=0.95,
        value=default_val,
        step=0.05,
        help="Filter out detections and trajectory coordinates below this confidence threshold."
    )


def render_system_status(status_str: str) -> None:
    """
    Renders a glowing connection status badge on the sidebar.
    """
    status_str = status_str.strip().lower()
    
    if status_str == "api":
        st.sidebar.markdown(
            "System Status: <span class='status-connected'>● CONNECTED (REST API)</span>",
            unsafe_allow_html=True
        )
    elif status_str == "standalone":
        st.sidebar.markdown(
            "System Status: <span class='status-standalone'>● STANDALONE (LOCAL LOGS)</span>",
            unsafe_allow_html=True
        )
    else:
        st.sidebar.markdown(
            "System Status: <span class='status-offline'>● NO TELEMETRY FOUND</span>",
            unsafe_allow_html=True
        )
