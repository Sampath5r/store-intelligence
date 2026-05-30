#!/usr/bin/env python3
"""
Dashboard Analytics Chart Components
Purplle Store Intelligence Challenge
"""

from typing import Dict, List, Any
import pandas as pd
import streamlit as st

def render_funnel_chart(funnel_data: Dict[str, Any]) -> None:
    """
    Renders the progressive retail conversion funnel stage chart and duration summary.
    """
    st.subheader("Customer Retail Journey Funnel Stage Conversion")
    st.markdown(
        "Stages track transitions from **Entrance (Awareness)** to **Browsing Floors (Consideration)** "
        "and **Billing Checkouts (Purchase)**."
    )
    
    funnel = funnel_data.get("funnel", {})
    counts = funnel.get("funnel_counts", {})
    rates = funnel.get("conversion_rates", {})
    
    if counts:
        # Build progressive DataFrame
        funnel_df = pd.DataFrame({
            "Retail Stage": ["1. Entrance", "2. Browsing Floors", "3. Billing Checkout"],
            "Unique Visitors": [
                counts.get("1_Entrance", 0),
                counts.get("2_Browsing", 0),
                counts.get("3_Checkout", 0)
            ]
        })
        
        col_chart, col_stats = st.columns([2, 1])
        
        with col_chart:
            # Render funnel using standard Streamlit bar chart
            st.bar_chart(data=funnel_df, x="Retail Stage", y="Unique Visitors", color="#a855f7")
            
        with col_stats:
            st.markdown("### Conversion Efficiency")
            st.markdown(f"**Browse Transition Rate:** `{rates.get('entrance_to_browse_pct', 0.0)}%` of entrants progressed to floor aisles.")
            st.markdown(f"**Browsing Checkout Conversion:** `{rates.get('browse_to_checkout_pct', 0.0)}%` of browsing shoppers completed checkouts.")
            st.markdown(f"**Store Purchase Conversion:** `{rates.get('entrance_to_checkout_pct', 0.0)}%` overall conversion rate.")
            
            # Display session durations
            summary = funnel_data.get("summary", {})
            st.markdown("---")
            st.markdown("### Session Durations")
            st.markdown(f"**Average Completed Session:** `{summary.get('average_completed_duration_sec', 0.0)}s` in store.")
            st.markdown(f"**Average Abandoned Session:** `{summary.get('average_abandoned_duration_sec', 0.0)}s` before dropout.")
    else:
        st.info("No funnel stage records captured for the current filters.")


def render_dwell_histogram(dwell_distribution: Dict[str, int]) -> None:
    """
    Renders a bar chart representing the distribution profile of visitor dwell times.
    """
    st.subheader("Dwell Time Distribution Profile")
    st.markdown("Counts how long visitors stay inside CCTV zones before leaving.")
    
    if dwell_distribution:
        dwell_df = pd.DataFrame({
            "Duration Span": list(dwell_distribution.keys()),
            "Customer Count": list(dwell_distribution.values())
        })
        st.bar_chart(data=dwell_df, x="Duration Span", y="Customer Count", color="#8b5cf6")
    else:
        st.info("No dwell data records captured.")


def render_camera_workload(camera_rankings: List[Dict[str, Any]]) -> None:
    """
    Renders camera workload rankings and unique customer comparisons.
    """
    st.subheader("Footprints and Workload by CCTV Camera")
    st.markdown("Ranks cameras based on unique visitor traffic and total signal logs.")
    
    if camera_rankings:
        cam_df = pd.DataFrame(camera_rankings)
        # Clean camera name formatting
        cam_df["camera_id"] = cam_df["camera_id"].apply(lambda x: x.split('_')[0].capitalize())
        cam_df.rename(
            columns={
                "camera_id": "Camera Zone",
                "unique_visitors": "Unique Visitors",
                "total_detections": "Total Signals"
            },
            inplace=True
        )
        
        st.dataframe(
            cam_df[["Camera Zone", "Unique Visitors", "Total Signals"]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No camera traffic ranks available.")
