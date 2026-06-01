import pytest

from app.models import CCTVEventPayload


@pytest.fixture()
def event_factory():
    """
    Reusable CCTV event builder for metrics, funnel, and anomaly tests.
    """

    def _make_event(
        track_id=1,
        timestamp=0.0,
        camera_id="entry_camera",
        event_type="update",
        bbox=None,
        confidence=0.9,
        dwell_time_sec=None,
    ):
        return CCTVEventPayload(
            timestamp=float(timestamp),
            camera_id=camera_id,
            track_id=int(track_id),
            bbox=bbox or [10, 10, 50, 90],
            confidence=float(confidence),
            event_type=event_type,
            dwell_time_sec=dwell_time_sec,
        )

    return _make_event


@pytest.fixture()
def retail_journey_events(event_factory):
    """
    Mixed retail journey sample with completed, abandoned, and active customers.
    """
    return [
        event_factory(1, 0.0, "entry_camera", "enter"),
        event_factory(1, 10000.0, "floor_camera1", "update"),
        event_factory(1, 40000.0, "billing_camera", "update"),
        event_factory(1, 50000.0, "billing_camera", "exit", dwell_time_sec=50.0),
        event_factory(2, 1000.0, "entry_camera", "enter"),
        event_factory(2, 15000.0, "floor_camera1", "update"),
        event_factory(2, 45000.0, "floor_camera1", "exit", dwell_time_sec=44.0),
        event_factory(3, 5000.0, "entry_camera", "enter"),
        event_factory(3, 8000.0, "floor_camera2", "update"),
        event_factory(3, 70000.0, "floor_camera2", "update"),
    ]


@pytest.fixture()
def anomaly_events(event_factory):
    """
    Compact event set that intentionally triggers each anomaly rule family.
    """
    overcrowding = [
        event_factory(track_id, 1000.0, "billing_camera", bbox=[10, 10, 30, 50])
        for track_id in range(1, 5)
    ]

    fast_motion = [
        event_factory(50, 0.0, "floor_camera1", bbox=[0, 0, 20, 20]),
        event_factory(50, 100.0, "floor_camera1", bbox=[400, 0, 420, 20]),
    ]

    loitering = [
        event_factory(60, 0.0, "entry_camera", bbox=[20, 20, 60, 80]),
        event_factory(60, 50000.0, "entry_camera", bbox=[22, 20, 62, 80]),
    ]

    restricted = [
        event_factory(70, 2000.0, "storage_area", bbox=[30, 30, 70, 90]),
        event_factory(70, 3000.0, "storage_area", bbox=[32, 30, 72, 90]),
    ]

    return overcrowding + fast_motion + loitering + restricted
