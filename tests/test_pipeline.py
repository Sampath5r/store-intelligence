import json
import uuid
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pytest

from pipeline.detect import process_video_pipeline
from pipeline.emit import EventEmitter, create_single_event
from pipeline.tracker import CCTVTracker, process_video_tracking


class FakeTensor:
    """
    Minimal tensor-like wrapper for the chained .cpu().numpy() calls used by YOLO results.
    """

    def __init__(self, value):
        self.value = np.array(value)

    def cpu(self):
        return self

    def numpy(self):
        return self.value


class FakeDetectionBox:
    """
    Emulates one Ultralytics detection box returned by model(frame).
    """

    def __init__(self, bbox, confidence=0.91, class_id=0):
        self.xyxy = [FakeTensor(bbox)]
        self.conf = [FakeTensor(confidence)]
        self.cls = [FakeTensor(class_id)]


class FakeDetectionResult:
    def __init__(self, boxes):
        self.boxes = boxes


class FakeDetectionModel:
    """
    Fast deterministic detection model that avoids loading YOLO weights in tests.
    """

    def __call__(self, frame, conf, classes, device, verbose):
        assert classes == [0]
        return [FakeDetectionResult([FakeDetectionBox([5, 6, 30, 35])])]


class FakeTrackBoxes:
    """
    Vectorized box container matching the attributes consumed by CCTVTracker.track_frame().
    """

    def __init__(self, boxes, track_ids, confidences):
        self.xyxy = FakeTensor(boxes)
        self.id = FakeTensor(track_ids)
        self.conf = FakeTensor(confidences)


class FakeTrackResult:
    def __init__(self, boxes):
        self.boxes = boxes


class FakeByteTrackModel:
    """
    Deterministic ByteTrack-like model for unit-testing tracker parsing.
    """

    def track(self, source, persist, conf, classes, device, tracker, verbose):
        assert persist is True
        assert tracker == "bytetrack.yaml"
        boxes = FakeTrackBoxes(
            boxes=[[10, 12, 34, 56], [40, 15, 60, 65]],
            track_ids=[7, 11],
            confidences=[0.88, 0.77],
        )
        return [FakeTrackResult(boxes)]


class FakePipelineTracker:
    """
    Small tracker double for exercising process_video_tracking() without model inference.
    """

    def __init__(self):
        self.unique_track_ids = set()
        self.calls = 0

    def track_frame(self, frame, conf_threshold=0.25):
        self.calls += 1
        track_id = 100 + self.calls
        self.unique_track_ids.add(track_id)
        return [
            {
                "track_id": track_id,
                "bbox": [8, 10, 28, 40],
                "centroid": [18, 25],
                "confidence": 0.84,
            }
        ]

    def draw_motion_paths(self, frame, tracks):
        return frame


@pytest.fixture()
def runtime_dir(request):
    """
    Uses a repo-local ignored directory because Windows temp ACLs can block tmp_path.
    """
    safe_name = "".join(char if char.isalnum() else "_" for char in request.node.name)
    path = Path(__file__).parent / "_runtime_pipeline" / f"{safe_name}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture()
def sample_video(runtime_dir):
    """
    Creates a tiny valid MP4 inside pytest temp storage for OpenCV pipeline tests.
    """
    video_path = runtime_dir / "sample.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, 5.0, (64, 48))
    assert writer.isOpened()

    for idx in range(3):
        frame = np.full((48, 64, 3), idx * 60, dtype=np.uint8)
        cv2.putText(frame, str(idx), (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        writer.write(frame)

    writer.release()
    return video_path


def test_detection_pipeline_writes_video_and_detection_metadata(sample_video, runtime_dir):
    output_video = runtime_dir / "detected.mp4"
    output_json = runtime_dir / "detections.json"

    result = process_video_pipeline(
        video_path=str(sample_video),
        output_video_path=str(output_video),
        output_detections_path=str(output_json),
        model=FakeDetectionModel(),
        conf_threshold=0.25,
        device="cpu",
    )

    with output_json.open("r", encoding="utf-8") as f:
        metadata = json.load(f)

    assert output_video.exists()
    assert result["total_frames"] == 3
    assert result["total_person_detections"] == 3
    assert metadata["metadata"]["total_frames_logged"] == 3
    assert metadata["frames"][0]["person_count"] == 1
    assert metadata["frames"][0]["detections"][0]["bbox"] == [5, 6, 30, 35]
    assert metadata["frames"][0]["detections"][0]["bbox_normalized"] == [
        5 / 64,
        6 / 48,
        30 / 64,
        35 / 48,
    ]


def test_cctv_tracker_parses_bytetrack_results_without_real_model():
    tracker = CCTVTracker.__new__(CCTVTracker)
    tracker.model = FakeByteTrackModel()
    tracker.device = "cpu"
    tracker.track_history = defaultdict(list)
    tracker.max_history_len = 30
    tracker.unique_track_ids = set()

    tracks = tracker.track_frame(np.zeros((72, 96, 3), dtype=np.uint8), conf_threshold=0.3)

    assert [track["track_id"] for track in tracks] == [7, 11]
    assert tracks[0]["bbox"] == [10, 12, 34, 56]
    assert tracks[0]["centroid"] == [22, 34]
    assert tracker.unique_track_ids == {7, 11}


def test_tracking_pipeline_writes_frame_telemetry(sample_video, runtime_dir):
    output_video = runtime_dir / "tracked.mp4"
    output_json = runtime_dir / "tracking_events.json"
    tracker = FakePipelineTracker()

    result = process_video_tracking(
        video_path=str(sample_video),
        output_video_path=str(output_video),
        output_events_path=str(output_json),
        tracker=tracker,
        conf_threshold=0.25,
    )

    with output_json.open("r", encoding="utf-8") as f:
        telemetry = json.load(f)

    assert output_video.exists()
    assert result["total_frames"] == 3
    assert result["total_unique_customers"] == 3
    assert telemetry["metadata"]["total_unique_customers"] == 3
    assert telemetry["frames"][0]["active_count"] == 1
    assert telemetry["frames"][0]["detections"][0]["centroid"] == [18, 25]
    assert telemetry["frames"][0]["detections"][0]["bbox_normalized"] == [
        8 / 64,
        10 / 48,
        28 / 64,
        40 / 48,
    ]


def test_event_emitter_generates_enter_update_exit_and_flush_events(runtime_dir):
    output_json = runtime_dir / "events.json"
    emitter = EventEmitter(
        camera_id="entry_camera",
        output_path=str(output_json),
        exit_timeout_ms=1000.0,
    )

    first_batch = emitter.process_frame_tracks(
        [{"track_id": 42, "bbox": [10, 20, 40, 80], "confidence": 0.92}],
        timestamp_ms=100.0,
    )
    second_batch = emitter.process_frame_tracks(
        [{"track_id": 42, "bbox": [12, 20, 42, 80], "confidence": 0.93}],
        timestamp_ms=500.0,
    )
    exit_batch = emitter.process_frame_tracks([], timestamp_ms=1700.0)

    assert [event.event_type for event in first_batch] == ["enter"]
    assert [event.event_type for event in second_batch] == ["update"]
    assert [event.event_type for event in exit_batch] == ["exit"]
    assert exit_batch[0].track_id == 42
    assert exit_batch[0].dwell_time_sec == 0.4

    with output_json.open("r", encoding="utf-8") as f:
        stored_events = json.load(f)

    assert [event["event_type"] for event in stored_events] == ["enter", "update", "exit"]
    assert emitter.flush(final_timestamp_ms=2000.0) == []


def test_create_single_event_validates_schema_fields():
    event = create_single_event(
        timestamp=123.0,
        camera_id="billing_camera",
        track_id=9,
        bbox=[1, 2, 3, 4],
        confidence=0.87,
        event_type="enter",
    )

    assert event.track_id == 9
    assert event.camera_id == "billing_camera"


def test_invalid_video_path_raises_for_detection_and_tracking(runtime_dir):
    missing_video = runtime_dir / "missing.mp4"

    with pytest.raises(FileNotFoundError):
        process_video_pipeline(
            video_path=str(missing_video),
            output_video_path=str(runtime_dir / "detected.mp4"),
            output_detections_path=str(runtime_dir / "detections.json"),
            model=FakeDetectionModel(),
        )

    with pytest.raises(FileNotFoundError):
        process_video_tracking(
            video_path=str(missing_video),
            output_video_path=str(runtime_dir / "tracked.mp4"),
            output_events_path=str(runtime_dir / "tracking.json"),
            tracker=FakePipelineTracker(),
        )


def test_event_emitter_rejects_malformed_track_payload(runtime_dir):
    emitter = EventEmitter(camera_id="entry_camera", output_path=str(runtime_dir / "events.json"))

    with pytest.raises(ValueError, match="missing required field"):
        emitter.process_frame_tracks(
            [{"track_id": 1, "confidence": 0.7}],
            timestamp_ms=100.0,
        )
