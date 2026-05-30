#!/usr/bin/env python3
"""
Dashboard Anomaly Table/Alert Component
Purplle Store Intelligence Challenge
"""

from typing import List, Dict, Any
import streamlit as st

def render_anomalies_panel(anomalies: List[Dict[str, Any]]) -> None:
    """
    Renders rule-based notifications styled dynamically by alert severity.
    """
    st.subheader("CCTV System Security & Overcrowding Alarms")
    st.markdown("Lists active alerts compiled from the retail rule-based engines.")
    
    if anomalies:
        for idx, alert in enumerate(anomalies):
            severity = alert.get("severity", "low").strip().lower()
            a_type = alert.get("anomaly_type", "Warning").replace('_', ' ').upper()
            camera = alert.get("camera_id", "Unknown").split('_')[0].capitalize()
            track_id = alert.get("track_id")
            details = alert.get("details", "")
            
            # Format title text
            track_badge = f" | Track ID: {track_id}" if track_id is not None else ""
            alert_header = f"**[{a_type}]** CCTV Zone: `{camera}`{track_badge}"
            
            # Draw color-coded notification cards depending on severity rating
            if severity == "high":
                st.error(f"{alert_header}  \n{details}")
            elif severity == "medium":
                st.warning(f"{alert_header}  \n{details}")
            else:
                st.info(f"{alert_header}  \n{details}")
    else:
        st.success("🎉 Excellent. System scan complete. Zero CCTV retail anomaly alerts recorded.")
