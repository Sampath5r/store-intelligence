from app.metrics import (
    calculate_customer_dwell_times,
    calculate_dwell_analytics,
    compile_dashboard_summary,
    detect_high_engagement_zones,
    get_camera_traffic_breakdown,
    get_active_visitors,
    get_peak_traffic_periods,
    get_total_unique_customers,
    reconstruct_customer_trajectories,
)
from app.funnel import (
    calculate_funnel_analytics,
    compile_funnel_dashboard,
    detect_abandoned_journeys,
    reconstruct_customer_sessions,
)


def test_people_counts_active_visitors_and_empty_edges(retail_journey_events):
    """
    Validates people count KPIs and empty-input defaults.
    """
    assert get_total_unique_customers(retail_journey_events) == 3
    assert get_active_visitors(retail_journey_events) == [3]
    assert get_total_unique_customers([]) == 0
    assert get_active_visitors([]) == []


def test_customer_dwell_uses_exit_duration_and_update_span_fallback(event_factory):
    """
    Explicit exit dwell values win; update-only tracks fall back to timestamp span.
    """
    events = [
        event_factory(1, 0.0, "entry_camera", "enter"),
        event_factory(1, 10000.0, "entry_camera"),
        event_factory(1, 20000.0, "entry_camera", "exit", dwell_time_sec=20.0),
        event_factory(2, 5000.0, "floor_camera", "enter"),
        event_factory(2, 45000.0, "floor_camera"),
        event_factory(2, 65000.0, "floor_camera", "exit", dwell_time_sec=60.0),
        event_factory(3, 10000.0, "floor_camera"),
        event_factory(3, 70000.0, "floor_camera"),
    ]

    dwell_rows = calculate_customer_dwell_times(events)
    by_track = {row["track_id"]: row for row in dwell_rows}

    assert by_track[1]["total_dwell_time_sec"] == 20.0
    assert by_track[2]["total_dwell_time_sec"] == 60.0
    assert by_track[3]["total_dwell_time_sec"] == 60.0
    assert by_track[3]["is_active"] is True


def test_dwell_summary_and_high_engagement_zones_are_generated(event_factory):
    """
    Checks aggregate dwell buckets and dwell-heavy zone ranking.
    """
    events = [
        event_factory(1, 0.0, "entry_camera", "enter"),
        event_factory(1, 20000.0, "entry_camera", "exit", dwell_time_sec=20.0),
        event_factory(2, 5000.0, "floor_camera", "enter"),
        event_factory(2, 65000.0, "floor_camera", "exit", dwell_time_sec=60.0),
        event_factory(3, 10000.0, "floor_camera"),
        event_factory(3, 70000.0, "floor_camera"),
    ]

    dwell_stats = calculate_dwell_analytics(events)
    high_engagement = detect_high_engagement_zones(events)
    summary = compile_dashboard_summary(events)

    assert dwell_stats["average_dwell_time_sec"] == 46.67
    assert dwell_stats["median_dwell_time_sec"] == 60.0
    assert dwell_stats["dwell_time_distribution"]["15s - 1m"] == 1
    assert dwell_stats["dwell_time_distribution"]["1m - 3m"] == 2
    assert high_engagement[0]["camera_id"] == "floor_camera"
    assert high_engagement[0]["total_dwell_time_sec"] == 120.0
    assert summary["kpis"]["highest_engagement_zone"] == "floor_camera"
    assert summary["customer_dwell_times"][0]["total_dwell_time_sec"] == 60.0


def test_active_visitors_treat_exit_as_final_same_timestamp_state(event_factory):
    """
    Exit events should close a track even when an update shares the timestamp.
    """
    events = [
        event_factory(5, 100.0, "entry_camera", "enter"),
        event_factory(5, 500.0, "entry_camera", "update"),
        event_factory(5, 500.0, "entry_camera", "exit", dwell_time_sec=0.4),
        event_factory(10, 600.0, "entry_camera", "update"),
    ]

    assert get_active_visitors(events) == [10]


def test_dashboard_summary_traffic_timeline_and_camera_rankings(retail_journey_events):
    """
    Verifies dashboard analytics glue: KPIs, traffic bins, trajectories, and camera rankings.
    """
    summary = compile_dashboard_summary(retail_journey_events)
    traffic_periods = get_peak_traffic_periods(retail_journey_events, interval_sec=30.0)
    trajectories = reconstruct_customer_trajectories(retail_journey_events)
    camera_rankings = get_camera_traffic_breakdown(retail_journey_events)

    assert summary["kpis"]["total_unique_customers"] == 3
    assert summary["kpis"]["active_occupancy"] == 1
    assert summary["dwell_analytics"]["total_customers_measured"] == 3
    assert traffic_periods[0]["visitor_count"] == 3
    assert trajectories[1][0]["camera_id"] == "entry_camera"
    assert trajectories[1][-1]["camera_id"] == "billing_camera"
    assert camera_rankings[0]["unique_visitors"] >= camera_rankings[-1]["unique_visitors"]


def test_funnel_analytics_counts_conversions_and_abandonment(retail_journey_events):
    """
    Validates stage counts, conversion rates, and abandoned journey samples.
    """
    sessions = reconstruct_customer_sessions(retail_journey_events)
    funnel = calculate_funnel_analytics(sessions)
    abandoned = detect_abandoned_journeys(sessions)
    dashboard = compile_funnel_dashboard(retail_journey_events)

    assert len(sessions) == 3
    assert sessions[1]["purchased"] is True
    assert sessions[2]["abandoned"] is True
    assert funnel["funnel_counts"] == {
        "1_Entrance": 3,
        "2_Browsing": 3,
        "3_Checkout": 1,
    }
    assert funnel["conversion_rates"]["entrance_to_browse_pct"] == 100.0
    assert funnel["conversion_rates"]["entrance_to_checkout_pct"] == 33.3
    assert len(abandoned) == 2
    assert dashboard["summary"]["completed_purchases"] == 1
    assert dashboard["summary"]["abandoned_journeys"] == 2


def test_metrics_and_funnel_empty_inputs_are_stable():
    """
    Empty analytics inputs should return predictable zero-value structures.
    """
    dwell = calculate_dwell_analytics([])
    summary = compile_dashboard_summary([])
    funnel = compile_funnel_dashboard([])

    assert dwell["total_customers_measured"] == 0
    assert summary["kpis"]["total_unique_customers"] == 0
    assert summary["traffic_timeline"] == []
    assert funnel["funnel"]["funnel_counts"]["1_Entrance"] == 0
    assert funnel["summary"]["total_sessions"] == 0
