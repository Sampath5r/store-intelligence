#!/usr/bin/env python3
"""
Dashboard Spatial Heatmap Component
Purplle Store Intelligence Challenge
"""

import os
from typing import List, Any
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

def render_spatial_heatmap(events: List[Any], camera_id: str = "All Cameras") -> None:
    """
    Renders customer spatial movement footprints.
    If a pre-generated computer vision heatmap overlaid on a CCTV frame exists,
    it displays it directly. Otherwise, it falls back to rendering a 2D density plot.
    """
    st.subheader("CCTV Spatial Bounding Box Footprint Heatmap")
    
    # 1. Primary: Try to load pre-generated CV overlaid heatmap image
    if camera_id != "All Cameras":
        heatmap_img_path = f"data/outputs/{camera_id}_heatmap.png"
        if os.path.exists(heatmap_img_path):
            st.image(
                heatmap_img_path,
                caption=f"CCTV Footprint Heatmap - {camera_id.split('_')[0].capitalize()}",
                use_container_width=True
            )
            st.markdown(
                "*(Thermal map displays visitor occupancy density overlaid directly on the CCTV stream frame.)*"
            )
            return
            
    # 2. Secondary/Fallback: Render 2D Matplotlib density plot from events log coordinates
    st.markdown("Simulates 2D density mapping of customer centroids extracted from tracking boxes.")
    
    if events:
        # Extract centroids coordinates
        x_coords = []
        y_coords = []
        
        for event in events:
            # Handle both Pydantic models and raw dict fallbacks
            bbox = getattr(event, "bbox", None) or event.get("bbox")
            if bbox and len(bbox) == 4:
                x1, y1, x2, y2 = bbox
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                x_coords.append(cx)
                y_coords.append(cy)
                
        if x_coords:
            # Plot a 2D density scatter plot using Matplotlib
            fig, ax = plt.subplots(figsize=(10, 5), facecolor='#1e1b4b')
            ax.set_facecolor('#0f172a')
            
            # Renders density scatter with semi-transparent alpha overlays
            scatter = ax.scatter(
                x_coords, y_coords,
                c='magenta',
                alpha=0.15,
                s=25,
                cmap='rainbow'
            )
            
            # Style overlay grids and headers
            ax.set_title("Retail Store Trajectory Density", color='white', fontsize=12, pad=10)
            ax.set_xlabel("X-Coordinate Pixels", color='gray')
            ax.set_ylabel("Y-Coordinate Pixels", color='gray')
            ax.tick_params(colors='gray')
            ax.grid(color='#334155', linestyle='--', alpha=0.3)
            
            # Invert y-axis to match coordinate grid standard in OpenCV (0,0 is top-left)
            ax.invert_yaxis()
            
            st.pyplot(fig)
        else:
            st.info("No coordinate detections recorded for heatmaps.")
    else:
        st.info("Ingest spatial coordinates telemetry to populate density heatmaps.")
