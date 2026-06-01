#!/usr/bin/env python3
"""
Customer movement heatmap generation for CCTV tracking outputs.

The module reads existing tracking/event JSON files, extracts tracked customer
coordinates, builds a CPU-friendly OpenCV/NumPy density map, and overlays the
result on CCTV frames. It is intentionally standalone so the batch runner,
dashboard, or other pipeline modules can reuse the same logic.
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np


Point = Tuple[float, float]


# ==============================================================================
# Logging
# ==============================================================================
def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    """
    Creates the shared heatmap logger without adding duplicate handlers.
    """
    logger = logging.getLogger("CCTV_Heatmap")
    logger.setLevel(log_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger()


@dataclass(frozen=True)
class HeatmapConfig:
    """
    Tunable parameters for static image and video-frame heatmap overlays.
    """

    radius: int = 25
    alpha: float = 0.55
    intensity_scale: float = 1.5
    colormap: int = cv2.COLORMAP_JET


# ==============================================================================
# Input Parsing
# ==============================================================================
def load_events_json(events_path: str) -> Any:
    """
    Loads tracking telemetry or emitted event JSON from disk.
    """
    if not os.path.exists(events_path):
        raise FileNotFoundError(f"Events JSON file not found: {events_path}")

    logger.info("Reading tracking coordinates from event JSON: %s", events_path)
    with open(events_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _as_float_pair(value: Any) -> Optional[Point]:
    """
    Converts common centroid forms into an (x, y) pair.
    """
    if isinstance(value, dict):
        x_val = value.get("x")
        y_val = value.get("y")
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        x_val = value[0]
        y_val = value[1]
    else:
        return None

    try:
        x = float(x_val)
        y = float(y_val)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(x) or not np.isfinite(y):
        return None

    return x, y


def _bbox_centroid(bbox: Any) -> Optional[Point]:
    """
    Computes a centroid from a [x1, y1, x2, y2] bounding box.
    """
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None

    try:
        x1, y1, x2, y2 = [float(coord) for coord in bbox]
    except (TypeError, ValueError):
        return None

    if not all(np.isfinite(coord) for coord in (x1, y1, x2, y2)):
        return None

    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _scale_normalized_point(point: Point, frame_size: Optional[Tuple[int, int]]) -> Point:
    """
    Supports event JSONs that store normalized [0, 1] coordinates.
    """
    if frame_size is None:
        return point

    width, height = frame_size
    x, y = point
    if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
        return x * width, y * height
    return point


def _event_to_point(event: Dict[str, Any], frame_size: Optional[Tuple[int, int]]) -> Optional[Point]:
    """
    Extracts one tracked coordinate from a single event/detection record.
    """
    # Tracker JSON already includes centroids; emitted events often only include bboxes.
    centroid = (
        _as_float_pair(event.get("centroid"))
        or _as_float_pair(event.get("center"))
        or _as_float_pair(event.get("point"))
    )
    if centroid is not None:
        return _scale_normalized_point(centroid, frame_size)

    bbox = event.get("bbox")
    if bbox is None and "bbox_normalized" in event and frame_size is not None:
        width, height = frame_size
        normalized = event["bbox_normalized"]
        if isinstance(normalized, (list, tuple)) and len(normalized) == 4:
            bbox = [
                float(normalized[0]) * width,
                float(normalized[1]) * height,
                float(normalized[2]) * width,
                float(normalized[3]) * height,
            ]

    centroid = _bbox_centroid(bbox)
    if centroid is None:
        return None

    return _scale_normalized_point(centroid, frame_size)


def iter_tracking_records(payload: Any) -> Iterable[Dict[str, Any]]:
    """
    Yields event-like dictionaries from supported telemetry formats.

    Supported formats:
    - EventEmitter output: [event, event, ...]
    - Wrapped event output: {"events": [...]}
    - Tracker output: {"frames": [{"detections": [...]}]}
    - Single event dictionary.
    """
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return

    if not isinstance(payload, dict):
        return

    if isinstance(payload.get("events"), list):
        for item in payload["events"]:
            if isinstance(item, dict):
                yield item
        return

    if isinstance(payload.get("frames"), list):
        for frame in payload["frames"]:
            if not isinstance(frame, dict):
                continue
            timestamp_ms = frame.get("timestamp_ms")
            frame_index = frame.get("frame_index")
            detections = frame.get("detections") or frame.get("tracks") or []
            for detection in detections:
                if isinstance(detection, dict):
                    enriched = dict(detection)
                    enriched.setdefault("timestamp", timestamp_ms)
                    enriched.setdefault("frame_index", frame_index)
                    yield enriched
        return

    yield payload


def extract_tracking_points(
    payload: Any,
    frame_size: Optional[Tuple[int, int]] = None,
) -> List[Point]:
    """
    Extracts all usable customer coordinates from an event JSON payload.
    """
    points: List[Point] = []

    for record in iter_tracking_records(payload):
        point = _event_to_point(record, frame_size)
        if point is not None:
            points.append(point)

    logger.info("Extracted %d customer coordinate point(s) for heatmap accumulation.", len(points))
    return points


# ==============================================================================
# Frame Loading and Heatmap Rendering
# ==============================================================================
def extract_background_frame(video_path: str, frame_index: int = 0) -> Tuple[np.ndarray, int, int]:
    """
    Extracts a CCTV frame to use as the heatmap background canvas.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    logger.info("Extracting CCTV background frame from: %s", video_path)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Failed to open video stream: {video_path}")

    try:
        if frame_index > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)

        ret, frame = cap.read()
        if not ret or frame is None:
            raise IOError(f"Could not read frame {frame_index} from video: {video_path}")

        height, width = frame.shape[:2]
        return frame, int(width), int(height)
    finally:
        cap.release()


def _odd_kernel_size(radius: int) -> int:
    """
    Maps a radius to a valid odd Gaussian kernel size.
    """
    radius = max(1, int(radius))
    return radius * 2 + 1


def accumulate_density_map(
    events_or_points: Sequence[Any],
    width: int,
    height: int,
    radius: int = 25,
) -> np.ndarray:
    """
    Builds a float32 customer density map from event records or point tuples.

    NumPy handles the coordinate accumulation; OpenCV handles the Gaussian
    smoothing. This keeps the hot path lightweight for CPU-only execution.
    """
    density = np.zeros((height, width), dtype=np.float32)
    if len(events_or_points) == 0:
        logger.warning("No points supplied; returning an empty density map.")
        return density

    first = events_or_points[0]
    if isinstance(first, dict):
        points = extract_tracking_points(events_or_points, frame_size=(width, height))
    else:
        points = [_as_float_pair(point) for point in events_or_points]
        points = [point for point in points if point is not None]

    if not points:
        logger.warning("No valid customer coordinates found inside the video frame.")
        return density

    # Clamp coordinates to the frame before accumulating so noisy boxes do not crash.
    coords = np.rint(np.asarray(points, dtype=np.float32)).astype(np.int32)
    xs = np.clip(coords[:, 0], 0, width - 1)
    ys = np.clip(coords[:, 1], 0, height - 1)
    np.add.at(density, (ys, xs), 1.0)

    kernel_size = _odd_kernel_size(radius)
    density = cv2.GaussianBlur(
        density,
        (kernel_size, kernel_size),
        sigmaX=float(radius),
        sigmaY=float(radius),
    )

    logger.info(
        "Accumulated %d point(s) into a %dx%d density map.",
        len(points),
        width,
        height,
    )
    return density


def normalize_density_map(density_map: np.ndarray, intensity_scale: float = 1.5) -> np.ndarray:
    """
    Converts a float32 density map to a visible uint8 mask.
    """
    if density_map.size == 0:
        return np.zeros_like(density_map, dtype=np.uint8)

    max_value = float(np.max(density_map))
    if max_value <= 0.0:
        return np.zeros(density_map.shape, dtype=np.uint8)

    normalized = density_map / max_value
    normalized = np.clip(normalized * max(0.01, float(intensity_scale)), 0.0, 1.0)
    return (normalized * 255.0).astype(np.uint8)


def apply_color_overlay(
    background_frame: np.ndarray,
    density_mask: np.ndarray,
    intensity_scale: float = 1.5,
    alpha: float = 0.55,
    colormap: int = cv2.COLORMAP_JET,
) -> np.ndarray:
    """
    Applies a thermal color map and blends it over a CCTV frame.
    """
    if background_frame.ndim != 3 or background_frame.shape[2] != 3:
        raise ValueError("background_frame must be a BGR image with shape HxWx3.")

    frame_height, frame_width = background_frame.shape[:2]
    if density_mask.shape[:2] != (frame_height, frame_width):
        density_mask = cv2.resize(
            density_mask,
            (frame_width, frame_height),
            interpolation=cv2.INTER_LINEAR,
        )

    alpha = float(np.clip(alpha, 0.0, 1.0))
    normalized_mask = normalize_density_map(density_mask, intensity_scale=intensity_scale)
    active_mask = normalized_mask > 0
    if not np.any(active_mask):
        return background_frame.copy()

    color_heatmap = cv2.applyColorMap(normalized_mask, colormap)
    blended = cv2.addWeighted(background_frame, 1.0 - alpha, color_heatmap, alpha, 0)

    # Keep untouched CCTV pixels fully original outside visited areas.
    output = background_frame.copy()
    output[active_mask] = blended[active_mask]
    return output


def save_image(output_path: str, image: np.ndarray) -> None:
    """
    Writes an image and raises if OpenCV fails to encode it.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if not cv2.imwrite(output_path, image):
        raise IOError(f"Failed to write heatmap image: {output_path}")


# ==============================================================================
# Public Generation APIs
# ==============================================================================
def generate_cctv_heatmap(
    video_path: str,
    events_path: str,
    output_path: str,
    intensity_scale: float = 1.5,
    alpha: float = 0.55,
    radius: int = 25,
    frame_index: int = 0,
) -> bool:
    """
    Generates one CCTV-frame heatmap image from tracked customer coordinates.
    """
    try:
        background, width, height = extract_background_frame(video_path, frame_index=frame_index)
        payload = load_events_json(events_path)
        points = extract_tracking_points(payload, frame_size=(width, height))

        if not points:
            logger.warning("Heatmap skipped because no usable tracking coordinates were found.")
            return False

        density = accumulate_density_map(points, width, height, radius=radius)
        heatmap_overlay = apply_color_overlay(
            background_frame=background,
            density_mask=density,
            intensity_scale=intensity_scale,
            alpha=alpha,
        )

        save_image(output_path, heatmap_overlay)
        logger.info("Heatmap overlay image saved to: %s", output_path)
        return True
    except Exception as exc:
        logger.error("Failed to generate CCTV heatmap overlay. Error: %s", exc)
        return False


def generate_cctv_heatmap_video(
    video_path: str,
    events_path: str,
    output_video_path: str,
    intensity_scale: float = 1.5,
    alpha: float = 0.55,
    radius: int = 25,
) -> bool:
    """
    Writes a video where the generated movement heatmap is overlaid on each frame.
    """
    if not os.path.exists(video_path):
        logger.error("Video file not found: %s", video_path)
        return False

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("Failed to open video stream: %s", video_path)
        return False

    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        payload = load_events_json(events_path)
        points = extract_tracking_points(payload, frame_size=(width, height))
        if not points:
            logger.warning("Heatmap video skipped because no usable tracking coordinates were found.")
            return False

        density = accumulate_density_map(points, width, height, radius=radius)

        os.makedirs(os.path.dirname(os.path.abspath(output_video_path)), exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))
        if not writer.isOpened():
            logger.error("Could not initialize heatmap VideoWriter: %s", output_video_path)
            return False

        frame_idx = 0
        logger.info("Writing heatmap overlay video to: %s", output_video_path)
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_idx += 1
                overlay = apply_color_overlay(
                    background_frame=frame,
                    density_mask=density,
                    intensity_scale=intensity_scale,
                    alpha=alpha,
                )
                writer.write(overlay)

                if frame_idx % 100 == 0 or frame_idx == total_frames:
                    logger.info("Heatmap video frame %d/%d", frame_idx, total_frames)
        finally:
            writer.release()

        logger.info("Heatmap overlay video saved to: %s", output_video_path)
        return True
    except Exception as exc:
        logger.error("Failed to generate heatmap overlay video. Error: %s", exc)
        return False
    finally:
        cap.release()


# ==============================================================================
# CLI
# ==============================================================================
def main() -> None:
    """
    CLI entrypoint for static image and optional full-video heatmap generation.
    """
    parser = argparse.ArgumentParser(
        description="Generate customer movement heatmaps from CCTV tracking event JSON."
    )
    parser.add_argument(
        "--video_path",
        type=str,
        required=True,
        help="Path to the input CCTV MP4 video.",
    )
    parser.add_argument(
        "--events_path",
        type=str,
        required=True,
        help="Path to tracking/event JSON containing customer coordinates.",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        required=True,
        help="Path to save the generated heatmap overlay image.",
    )
    parser.add_argument(
        "--output_video_path",
        type=str,
        default="",
        help="Optional MP4 path for a full-frame heatmap overlay video.",
    )
    parser.add_argument(
        "--frame_index",
        type=int,
        default=0,
        help="Video frame index to use as the static heatmap background.",
    )
    parser.add_argument(
        "--intensity",
        type=float,
        default=1.5,
        help="Heatmap intensity multiplier (default: 1.5).",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.55,
        help="Heatmap overlay opacity from 0.0 to 1.0 (default: 0.55).",
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=25,
        help="Gaussian smoothing radius in pixels (default: 25).",
    )

    args = parser.parse_args()

    image_ok = generate_cctv_heatmap(
        video_path=args.video_path,
        events_path=args.events_path,
        output_path=args.output_path,
        intensity_scale=args.intensity,
        alpha=args.alpha,
        radius=args.radius,
        frame_index=args.frame_index,
    )

    video_ok = True
    if args.output_video_path:
        video_ok = generate_cctv_heatmap_video(
            video_path=args.video_path,
            events_path=args.events_path,
            output_video_path=args.output_video_path,
            intensity_scale=args.intensity,
            alpha=args.alpha,
            radius=args.radius,
        )

    if not image_ok or not video_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
