#!/usr/bin/env python3
"""
CCTV Customer Spatial Heatmap Overlay Generator
Purplle Store Intelligence Challenge

This module provides a CPU-optimized, high-fidelity computer vision pipeline
to accumulate customer tracking coordinates, smooth them using Gaussian grids,
apply thermal colormaps, and overlay them on CCTV background frames.
"""

import os
import sys
import json
import logging
import argparse
from typing import Dict, List, Any, Tuple, Optional

import cv2
import numpy as np

# ==============================================================================
# Logging Configuration
# ==============================================================================
def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a standardized logger for the heatmap generator.
    """
    logger = logging.getLogger("CCTV_Heatmap")
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
# Core Heatmap Generation Operations
# ==============================================================================

def extract_background_frame(video_path: str) -> Tuple[np.ndarray, int, int]:
    """
    Extracts the first frame of the CCTV video to serve as the background canvas.
    Returns the frame (BGR) and its width and height.
    """
    if not os.path.exists(video_path):
        logger.error(f"Video source not found at: {video_path}")
        raise FileNotFoundError(f"Video file not found: {video_path}")
        
    logger.info(f"Extracting base background canvas from video: {video_path}")
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        logger.error("Failed to open CCTV video cap stream.")
        raise IOError("Failed to open video stream.")
        
    ret, frame = cap.read()
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    
    if not ret or frame is None:
        logger.warning("Could not extract a valid frame from video. Generating fallback black canvas.")
        # Fallback to a neutral, dark canvas if video frame extraction fails
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        width, height = 1280, 720
        
    return frame, width, height


def accumulate_density_map(
    events: List[Dict[str, Any]],
    width: int,
    height: int,
    radius: int = 15
) -> np.ndarray:
    """
    Accumulates customer coordinate centroids into a single floating-point density mask
    and applies a Gaussian blur to smooth the spatial thermal layout.
    """
    # Create empty, float32 accumulation mask
    density_mask = np.zeros((height, width), dtype=np.float32)
    
    logger.info(f"Accumulating coordinates from {len(events)} telemetry data points...")
    coordinate_count = 0
    
    for event in events:
        # Resolve bounding box coordinates dynamically
        bbox = event.get("bbox")
        if bbox and len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            
            # Bound check coordinates
            if 0 <= cx < width and 0 <= cy < height:
                # Add localized heat signature at centroid
                # Draw a filled circle on the float32 accumulation mask
                cv2.circle(density_mask, (cx, cy), radius, 1.0, -1)
                coordinate_count += 1
                
    logger.info(f"Successfully mapped {coordinate_count} spatial centroids to density mask.")
    
    if coordinate_count > 0:
        # Apply Gaussian Blur to smooth the discrete points into a continuous thermal layout
        # Kernel size must be odd and greater than zero
        kernel_size = radius * 2 + 1
        density_mask = cv2.GaussianBlur(density_mask, (kernel_size, kernel_size), 0)
        
    return density_mask


def apply_color_overlay(
    background_frame: np.ndarray,
    density_mask: np.ndarray,
    intensity_scale: float = 10.0,
    alpha: float = 0.5
) -> np.ndarray:
    """
    Applies a thermal colormap on the scaled density mask, and blends it
    translucently over the base CCTV background frame.
    """
    # 1. Scale and normalize the density mask to standard uint8 limits [0, 255]
    scaled_density = density_mask * intensity_scale
    normalized_mask = np.clip(scaled_density * 255.0, 0, 255).astype(np.uint8)
    
    # 2. Prevent color leakage on unvisited surfaces by creating a zero-intensity mask
    zero_mask = normalized_mask == 0
    
    # 3. Apply standard highly visible thermal colormap (cv2.COLORMAP_JET)
    color_heatmap = cv2.applyColorMap(normalized_mask, cv2.COLORMAP_JET)
    
    # Force zero-occupancy regions to black to avoid colormap leak
    color_heatmap[zero_mask] = 0
    
    # 4. Translucently blend the color heatmap overlay directly onto the base CCTV frame
    # overlaid = background * (1 - alpha) + heatmap * alpha
    # For regions with zero occupancy, we want to retain 100% of the background frame
    overlaid_frame = background_frame.copy()
    
    # Apply alpha blending only on areas visited by customers
    visit_mask = ~zero_mask
    overlaid_frame[visit_mask] = cv2.addWeighted(
        background_frame,
        1.0 - alpha,
        color_heatmap,
        alpha,
        0
    )[visit_mask]
    
    return overlaid_frame

# ==============================================================================
# Unified Master Execution
# ==============================================================================
def generate_cctv_heatmap(
    video_path: str,
    events_path: str,
    output_path: str,
    intensity_scale: float = 10.0,
    alpha: float = 0.5,
    radius: int = 15
) -> bool:
    """
    Coordinates base frame extraction, coordinates mapping, Gaussian smoothing,
    colormap blending, and persists the generated heatmap image.
    """
    if not os.path.exists(events_path):
        logger.error(f"Events JSON telemetry log file not found at: {events_path}")
        return False
        
    logger.info(f"Reading events telemetry log file: {events_path}")
    try:
        with open(events_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read or parse events JSON file. Error: {e}")
        return False
        
    # Unpack events array dynamically supporting dual formats (frame logs vs event lists)
    raw_events: List[Dict[str, Any]] = []
    
    if isinstance(data, list):
        # Format A: List of events (e.g. outputs from pipeline/emit.py)
        raw_events = data
    elif isinstance(data, dict):
        if "events" in data and isinstance(data["events"], list):
            raw_events = data["events"]
        elif "frames" in data and isinstance(data["frames"], list):
            # Format B: Frame-level coordinate dumps (e.g. outputs from pipeline/tracker.py)
            for frame in data["frames"]:
                detections = frame.get("detections", [])
                for det in detections:
                    raw_events.append(det)
                    
    if not raw_events:
        logger.warning("No tracking coordinate events found in log file. Heatmap cannot be generated.")
        return False
        
    try:
        # Step 1: Extract Background CCTV Frame
        background, width, height = extract_background_frame(video_path)
        
        # Step 2: Accumulate Density Bins and Smooth
        density = accumulate_density_map(raw_events, width, height, radius=radius)
        
        # Step 3: Colorize and Translucently Overlay
        heatmap_overlay = apply_color_overlay(
            background_frame=background,
            density_mask=density,
            intensity_scale=intensity_scale,
            alpha=alpha
        )
        
        # Step 4: Persist Heatmap Output Image
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        cv2.imwrite(output_path, heatmap_overlay)
        logger.info(f"[SUCCESS] Heatmap overlay successfully saved to: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to generate CCTV heatmap overlay. Error: {e}")
        return False

# ==============================================================================
# CLI Entrypoint
# ==============================================================================
def main() -> None:
    """
    Configures parser command line arguments and runs heatmap generator.
    """
    parser = argparse.ArgumentParser(
        description="CCTV Customer Spatial Heatmap Overlay Generator using OpenCV"
    )
    parser.add_argument(
        "--video_path",
        type=str,
        required=True,
        help="Path to the input CCTV MP4 video file to extract background frame."
    )
    parser.add_argument(
        "--events_path",
        type=str,
        required=True,
        help="Path to the telemetry events JSON log containing tracking coordinates."
    )
    parser.add_argument(
        "--output_path",
        type=str,
        required=True,
        help="Path to save the generated overlaid PNG heatmap image."
    )
    parser.add_argument(
        "--intensity",
        type=float,
        default=10.0,
        help="Heat intensity multiplier scale factor (default: 10.0)."
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.55,
        help="Opacity transparency factor of colormap overlay (default: 0.55)."
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=15,
        help="Gaussian blur radius of coordinate density points (default: 15)."
    )
    
    args = parser.parse_args()
    
    success = generate_cctv_heatmap(
        video_path=args.video_path,
        events_path=args.events_path,
        output_path=args.output_path,
        intensity_scale=args.intensity,
        alpha=args.alpha,
        radius=args.radius
    )
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
