#!/usr/bin/env python3
"""
Dashboard KPI Card Components
Purplle Store Intelligence Challenge
"""

from typing import Dict, Any
import streamlit as st

def render_kpi_cards(kpi_data: Dict[str, Any], connection_status: str) -> None:
    """
    Renders the KPI card metrics block across 5 grid columns.
    """
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            "Total Customers Tracked",
            f"{kpi_data.get('total_unique_customers', 0)}",
            help="Cumulative count of unique customer tracking IDs registered in streams."
        )
        
    with col2:
        st.metric(
            "Active Floor Occupancy",
            f"{kpi_data.get('active_occupancy', 0)}",
            help="Estimate of customers currently detected inside the store aisles."
        )
        
    with col3:
        st.metric(
            "Average Dwell Time",
            f"{kpi_data.get('average_dwell_time_sec', 0.0)}s",
            help="Average duration spent by customers within active camera views."
        )
        
    with col4:
        busiest_raw = kpi_data.get('busiest_camera_zone', 'N/A')
        # Clean naming representation (e.g. entry_camera -> Entry)
        busiest_clean = busiest_raw.split('_')[0].capitalize() if busiest_raw != "N/A" else "N/A"
        st.metric(
            "Busiest CCTV Aisle",
            busiest_clean,
            help="CCTV camera zone recording the highest footprints and signal traffic."
        )
        
    with col5:
        # Map diagnostic status
        status_grade = "HEALTHY" if connection_status == "api" else "STANDALONE"
        st.metric(
            "System Core Status",
            status_grade,
            help="Platform data link connection diagnostics rating."
        )
