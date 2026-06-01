import numpy as np

from pipeline.heatmap import (
    accumulate_density_map,
    apply_color_overlay,
    extract_tracking_points,
)


def test_extract_tracking_points_supports_tracker_and_event_formats():
    tracker_payload = {
        "frames": [
            {
                "frame_index": 1,
                "timestamp_ms": 40.0,
                "detections": [
                    {"track_id": 1, "centroid": [10, 20], "bbox": [0, 0, 20, 40]},
                    {"track_id": 2, "bbox": [30, 40, 50, 80]},
                ],
            }
        ]
    }
    event_payload = [
        {
            "timestamp": 40.0,
            "camera_id": "entry_camera",
            "track_id": 3,
            "bbox": [100, 120, 140, 180],
            "confidence": 0.9,
            "event_type": "update",
        }
    ]

    tracker_points = extract_tracking_points(tracker_payload, frame_size=(200, 200))
    event_points = extract_tracking_points(event_payload, frame_size=(200, 200))

    assert tracker_points == [(10.0, 20.0), (40.0, 60.0)]
    assert event_points == [(120.0, 150.0)]


def test_density_map_overlay_changes_only_when_points_exist():
    frame = np.zeros((80, 100, 3), dtype=np.uint8)
    density = accumulate_density_map([(25, 25), (50, 30), (75, 70)], 100, 80, radius=5)
    overlay = apply_color_overlay(frame, density, intensity_scale=1.5, alpha=0.55)

    assert density.shape == (80, 100)
    assert float(density.max()) > 0.0
    assert overlay.shape == frame.shape
    assert np.count_nonzero(overlay) > 0
