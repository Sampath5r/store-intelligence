from app.anomalies import (
    analyze_store_anomalies,
    detect_loitering_anomalies,
    detect_overcrowding_anomalies,
    detect_restricted_access_anomalies,
    detect_unusual_movement_anomalies,
)


def test_overcrowding_anomaly_flags_capacity_breach(anomaly_events):
    """
    Billing has capacity 3; fixture puts 4 unique tracks in the same time bin.
    """
    alerts = detect_overcrowding_anomalies(anomaly_events)

    billing_alerts = [alert for alert in alerts if alert.camera_id == "billing_camera"]
    assert len(billing_alerts) == 1
    assert billing_alerts[0].anomaly_type == "overcrowding"
    assert billing_alerts[0].severity == "medium"


def test_unusual_movement_anomaly_uses_centroid_velocity(anomaly_events):
    """
    Track 50 jumps hundreds of pixels in 100ms, crossing the speed threshold.
    """
    alerts = detect_unusual_movement_anomalies(anomaly_events)

    assert len(alerts) == 1
    assert alerts[0].track_id == 50
    assert alerts[0].anomaly_type == "unusual_movement"
    assert alerts[0].severity == "high"


def test_loitering_anomaly_uses_zone_dwell_limit(anomaly_events):
    """
    Track 60 remains in entry_camera for 50s, exceeding the 45s limit.
    """
    alerts = detect_loitering_anomalies(anomaly_events)

    assert len(alerts) == 1
    assert alerts[0].track_id == 60
    assert alerts[0].camera_id == "entry_camera"
    assert alerts[0].anomaly_type == "long_idle_duration"


def test_restricted_access_anomaly_deduplicates_per_track_and_zone(anomaly_events):
    """
    Multiple storage_area events for one track should produce only one security alert.
    """
    alerts = detect_restricted_access_anomalies(anomaly_events)

    assert len(alerts) == 1
    assert alerts[0].track_id == 70
    assert alerts[0].camera_id == "storage_area"
    assert alerts[0].anomaly_type == "restricted_zone_access"


def test_anomaly_master_output_contains_all_rule_families(anomaly_events):
    """
    The aggregate anomaly API should include every rule family represented in fixtures.
    """
    alerts = analyze_store_anomalies(anomaly_events)
    alert_types = {alert.anomaly_type for alert in alerts}

    assert {
        "overcrowding",
        "unusual_movement",
        "long_idle_duration",
        "restricted_zone_access",
    }.issubset(alert_types)
    assert len(alerts) == 4


def test_anomaly_detectors_return_empty_lists_for_empty_inputs():
    """
    Edge-case guard: empty event lists should not create alerts.
    """
    assert detect_overcrowding_anomalies([]) == []
    assert detect_unusual_movement_anomalies([]) == []
    assert detect_loitering_anomalies([]) == []
    assert detect_restricted_access_anomalies([]) == []
    assert analyze_store_anomalies([]) == []


def test_overcrowding_does_not_alert_at_capacity_limit(event_factory):
    """
    Occupancy must exceed capacity, not merely equal it.
    """
    events = [
        event_factory(track_id, 1000.0, "billing_camera")
        for track_id in range(1, 4)
    ]

    assert detect_overcrowding_anomalies(events) == []


def test_unusual_movement_ignores_zero_time_and_cross_camera_jumps(event_factory):
    """
    Movement rules require positive frame time and the same CCTV camera.
    """
    zero_time_jump = [
        event_factory(81, 1000.0, "floor_camera1", bbox=[0, 0, 20, 20]),
        event_factory(81, 1000.0, "floor_camera1", bbox=[400, 0, 420, 20]),
    ]
    cross_camera_jump = [
        event_factory(82, 1000.0, "floor_camera1", bbox=[0, 0, 20, 20]),
        event_factory(82, 1100.0, "floor_camera2", bbox=[400, 0, 420, 20]),
    ]

    assert detect_unusual_movement_anomalies(zero_time_jump) == []
    assert detect_unusual_movement_anomalies(cross_camera_jump) == []


def test_idle_duration_does_not_alert_at_exact_limit(event_factory):
    """
    Loitering uses a strict greater-than threshold for zone dwell duration.
    """
    events = [
        event_factory(90, 0.0, "entry_camera"),
        event_factory(90, 45000.0, "entry_camera"),
    ]

    assert detect_loitering_anomalies(events) == []


def test_restricted_access_ignores_allowed_zones(event_factory):
    """
    Regular retail zones should not produce restricted access alerts.
    """
    events = [
        event_factory(91, 0.0, "entry_camera"),
        event_factory(91, 1000.0, "floor_camera1"),
        event_factory(91, 2000.0, "billing_camera"),
    ]

    assert detect_restricted_access_anomalies(events) == []
