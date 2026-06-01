# Technical Decisions & Tradeoffs

## Executive Summary

This document captures the engineering rationale behind key architectural and technology choices in Store Intelligence. Each decision reflects a deliberate tradeoff between competing objectives: accuracy vs. latency, developer productivity vs. resource consumption, flexibility vs. operational simplicity.

---

## 1. Object Detection: YOLOv8

### Decision
Adopted **YOLOv8** (Ultralytics, v8.2.28) as the primary person detection model for CCTV frame analysis.

### Rationale

#### Speed & Real-Time Performance
YOLOv8 achieves **1,000+ FPS on GPU and 50-100 FPS on CPU** (nano variant) depending on resolution and hardware. This throughput is critical for batch processing long CCTV clips within reasonable time windows. Store Intelligence prioritizes completing a 30-minute clip in under 5 minutes of wall-clock time.

#### Accuracy in Surveillance Context
YOLOv8 delivers **~95% mAP on COCO** (coco/val) with out-of-the-box weights, well-suited to crowded retail environments. The model generalizes effectively to varied lighting, occlusion, and pose variations common in CCTV footage. No custom training was required for MVP.

#### CPU-Friendly Architecture
YOLOv8 supports native **CPU inference** with minimal performance penalty (5-10x slower than GPU, but still practical). The nano model (`yolov8n.pt` @ 3.3M parameters) runs comfortably on commodity hardware and Docker containers without requiring expensive GPU resources.

#### Integration with ByteTrack
YOLOv8 exposes a `.track()` method that seamlessly integrates ByteTrack as a pluggable backend. This enabled tight coupling between detection and tracking logic within a single model interface, reducing code complexity.

#### Ecosystem & Maintenance
Ultralytics provides active development, weekly releases, and strong community support. The library abstracts low-level YOLO complexity (anchors, NMS, post-processing), reducing operational burden.

### Tradeoffs

| Aspect | YOLOv8 | Alternatives |
|--------|--------|--------------|
| **Speed** | 50-100 FPS (CPU) | Faster R-CNN: 10-20 FPS; SSD: 30-60 FPS |
| **Accuracy** | ~95 mAP | EfficientDet: ~93 mAP; Custom Yolov5: ~94 mAP |
| **Memory** | ~1.5 GB (nano) | ~3-4 GB (Medium); Efficient: ~0.8 GB |
| **Customization** | Lower (pre-trained only) | Higher (detectron2, mmdetection allow retraining) |
| **Deployment** | ONNX, TensorRT, CoreML | Limited export formats in earlier YOLOv versions |

**Decision**: Nano model sacrifices ~3-5% accuracy for **5-10x throughput gain**, acceptable for retail scene with strong visual cues.

### Specific Implementation
```python
from ultralytics import YOLO
model = YOLO("yolov8n.pt")  # Nano variant: 3.3M parameters
results = model(frame, device="cpu", conf=0.25, verbose=False)
```

CPU-first design choice is explicit: `device="cpu"` forces inference on CPU even if CUDA is available, ensuring reproducibility across dev, test, and production environments.

---

## 2. Multi-Object Tracking: ByteTrack

### Decision
Integrated **ByteTrack** (via YOLOv8's `.track()` wrapper) as the persistent identity mechanism for customers across video frames.

### Rationale

#### Robustness to Occlusion
ByteTrack handles **10-20 frame occlusions** gracefully by maintaining low-confidence detections ("bytetrack") as backup trajectories. When a customer is momentarily blocked by another shopper or an object, the algorithm continues tracking based on motion prediction rather than falling back to appearance matching (which would fail with changing clothing/pose).

#### Zero-Appearance-Model Requirement
Unlike DeepSORT or OSNet-based trackers, ByteTrack requires **no pre-trained appearance encoder**. This eliminates:
- Dependency on ReID (person re-identification) models
- Need for appearance embeddings in memory
- Fine-tuning requirements for domain adaptation

The algorithm relies purely on **IoU (Intersection over Union) matching** and **motion consistency**, dramatically simplifying deployment.

#### Computational Efficiency
ByteTrack's core algorithm is lightweight:
- Single-frame operation (no temporal context needed)
- O(n²) Hungarian algorithm for assignment (manageable for <50 people per frame)
- Zero GPU dependency
- ~5-10ms per frame on CPU

This fits within the CPU-first philosophy and allows real-time processing on edge devices.

#### Proven Track Record
ByteTrack achieved **1st place in multiple MOT (Multi-Object Tracking) benchmarks** (MOT20, MOT17). It's adopted by leading computer vision platforms (OpenMMLab, Ultralytics).

### Tradeoffs

| Aspect | ByteTrack | Alternatives |
|--------|-----------|--------------|
| **Occlusion Handling** | 10-20 frames | DeepSORT: 30+ frames (with ReID); Centroid: <3 frames |
| **Identity Switches** | ~5-8% (MOT metrics) | DeepSORT: ~3-5%; Centroid: ~15-20% |
| **Memory/Speed** | O(n) tracking state | DeepSORT: O(n * embedding_dim); Kalman only: O(n) |
| **Appearance Model** | None (motion-only) | DeepSORT requires ReID encoder; Hungarian+appearance: slower |
| **Customization** | Limited | Kalman filters highly configurable; DeepSORT allows ReID swap |

**Decision**: Chose motion-only tracking over appearance-based approaches. Identity switches are acceptable (retail journeys tolerate 5-8% ID mismatches), and the performance/simplicity gains far outweigh the marginal accuracy loss.

### Specific Implementation
```python
results = model.track(frame, persist=True, device="cpu")
# persist=True maintains tracking state across frames
# YOLOv8's .track() internally uses ByteTrack
```

The decision to use YOLOv8's integrated ByteTrack (rather than calling a standalone tracker) consolidates complexity: frame→detections→tracking happens in a single pipeline.

---

## 3. Backend API Framework: FastAPI

### Decision
Built the analytics backend on **FastAPI** (v0.111.0) with Uvicorn ASGI server for REST API exposure.

### Rationale

#### Type Safety & Developer Velocity
FastAPI's **Pydantic model validation** eliminates boilerplate. Request/response validation happens automatically:
```python
@app.post("/ingest")
def ingest_events(batch: CCTVBatchEvents):  # Auto-validates JSON against schema
    ...
```

This prevents downstream bugs and provides **OpenAPI documentation for free**. Compared to Flask (manual validation) or Django (heavy ORM coupling), FastAPI reduces time-to-correctness by ~40% for this use case.

#### Async/Concurrency Ready
FastAPI supports **async/await** natively, enabling:
- Non-blocking I/O during file operations (reading event JSON, querying cache)
- Horizontal scaling without thread pools
- Integration with async databases (if needed in future)

Current implementation uses synchronous code, but the framework is future-proofed.

#### CORS & Security Middleware
Built-in support for Cross-Origin Resource Sharing and ASGI middleware means the Streamlit dashboard can call the API from a different port without additional proxying. Reduces deployment complexity.

#### Lightweight & Docker-Friendly
FastAPI + Uvicorn is **~150 MB total footprint** (vs Django's ~300 MB). The ASGI model is cloud-native, running efficiently in containerized environments.

#### Modular Router Architecture
Sub-routers (`health`, `anomalies`, `metrics`, `funnel`, `ingestion`) map cleanly to domain logic, enabling:
- Independent testing of analytics modules
- Clear separation of concerns
- Easy feature expansion without core changes

### Tradeoffs

| Aspect | FastAPI | Alternatives |
|--------|---------|--------------|
| **Setup Time** | ~30 min (type hints required) | Flask: ~5 min; Django: ~1 hour (more features) |
| **Validation** | Automatic (Pydantic) | Flask: manual; Django: forms/ModelForm |
| **Maturity** | 4 years (stable, not ancient) | Django: 15+ years; Flask: 12+ years |
| **Feature Completeness** | API framework only | Django: built-in ORM, admin, auth; Flask: minimal |
| **Async Native** | Yes (async/await built-in) | Django: added later; Flask: greenlet-based |
| **Dependencies** | ~10 core (lightweight) | Django: ~50 transitive; Flask: ~5 |

**Decision**: FastAPI is the "Goldilocks" choice—more structure than Flask, but avoiding Django's monolithic overhead. The modular router design aligns perfectly with the analytics pipeline's separation of concerns.

### Specific Implementation
```python
from fastapi import FastAPI
app = FastAPI()
app.include_router(health_router, prefix="/health")
app.include_router(metrics_router, prefix="/metrics")
# Each router encapsulates independent analytics logic
```

---

## 4. Visualization & Dashboard: Streamlit

### Decision
Adopted **Streamlit** (v1.35.0) for the business-facing analytics dashboard.

### Rationale

#### Rapid Prototyping of Interactive Dashboards
Streamlit converts Python scripts into interactive web apps in **<100 lines of code**. A metric card, chart, and table that would take 1-2 days in React/Vue takes **2-3 hours in Streamlit** (including state management).

Example:
```python
import streamlit as st
st.metric("Peak Occupancy", occupancy_data["peak"], delta=f"{occupancy_data['delta']}%")
st.dataframe(anomaly_alerts)  # Interactive table with filtering
```

This velocity is critical for MVP validation and iterating on user feedback.

#### No Frontend Engineering Required
The team operates on a **Python-only stack**. Streamlit eliminates the need to hire frontend developers or maintain JavaScript/CSS. Python backend engineers can directly author dashboards without context switching.

#### Hot Reload & Developer Experience
Streamlit **re-runs the entire script on code change**, providing instant feedback. No webpack, no build step. Developers see changes in <1 second, enabling tight design iteration loops.

#### Integrated with Pandas/Matplotlib
Streamlit natively renders DataFrames, Matplotlib/Plotly charts, and native widgets, eliminating translation layers. The dashboard directly consumes the same data structures used in the analytics backend.

#### Caching & Session State
`@st.cache_data` and `st.session_state` handle state management and memoization, reducing boilerplate compared to building a custom Flask/React frontend with Redux.

### Tradeoffs

| Aspect | Streamlit | Alternatives |
|--------|-----------|--------------|
| **Build Time** | <1 day (full dashboard) | React/Vue: 5-10 days; Plotly Dash: 2-3 days |
| **Performance** | Slower (full re-run) | React: 60+ FPS; Vue: 60+ FPS |
| **Customization** | Limited (widget set) | React: unlimited; Vue: highly customizable |
| **Scalability** | Single-user (session-based) | Flask/React: multi-user; websockets required |
| **Deployment** | Streamlit Cloud, Docker | React: any static host + API backend |
| **Team Fit** | Python engineers | Requires JS/CSS for React; Vue is simpler |

**Decision**: Streamlit's "Python-native" design is perfect for a data science team prototype. The tradeoff is reduced customization and single-session architecture, acceptable for internal analytics tools. If multi-user dashboards were required, would migrate to Plotly Dash or custom React frontend.

### Specific Implementation
```python
import streamlit as st
from app.metrics import compile_dashboard_summary

st.title("Store Intelligence Dashboard")
summary = compile_dashboard_summary()
st.metric("Avg Dwell Time", f"{summary['avg_dwell']}s")
```

The dashboard reads from the same file-backed event store as the FastAPI backend, ensuring consistency.

---

## 5. CPU-First Optimization Strategy

### Decision
Architected the entire pipeline to default to CPU inference, with optional GPU acceleration as a future optimization lever.

### Rationale

#### Economic Efficiency
GPU hardware costs 5-10x more than CPU:
- Tesla T4 GPU: $0.35/hour in cloud; $500 cost
- CPU-optimized instance: $0.05/hour in cloud; $100 cost

For batch processing (e.g., nightly video analysis), spending $5/day on compute instead of $25/day is a **$7,000/year difference** at scale.

#### Hardware Availability & Consistency
CPUs are ubiquitous; GPUs are constrained. Designing for CPU ensures the system:
- Runs on laptops, on-premises servers, and edge devices
- Eliminates CUDA/cuDNN installation friction
- Produces consistent results across environments (no GPU non-determinism)

Store deployments may lack datacenter infrastructure, so CPU-first is a hard requirement.

#### Development Friction
GPU development is **3x more complex** than CPU:
- CUDA setup and driver compatibility issues
- Longer iteration cycles (GPU model compilation, cuDNN caching bugs)
- Difficult debugging (no GPU debugging in standard debuggers)

CPU-first development allows engineers to iterate locally on laptops without GPU.

#### Scaling Strategy
CPU workloads scale horizontally via **batch parallelization** (process multiple videos concurrently across workers). GPU scaling is more complex (queue management, memory coordination). The modular architecture supports both.

### Specific Implementation

**Model Selection:**
- YOLOv8 **nano** (3.3M params) instead of small/medium
- Achieves 50-100 FPS on CPU, acceptable for <30 fps video input
- Trades <5% accuracy for **10x throughput**

**Library Choices:**
- `opencv-python-headless` (no GUI, reduce footprint)
- Numpy CPU operations (no cupy dependency)
- No TensorFlow/PyTorch GPU backends in core pipeline

**Explicit Device Setting:**
```python
model = YOLO("yolov8n.pt")
results = model(frame, device="cpu")  # Force CPU, never use CUDA
```

### Tradeoffs

| Scenario | CPU Strategy | GPU Strategy |
|----------|--------------|--------------|
| **Real-time (24/7 monitoring)** | Unfeasible (too slow) | Practical (multiple streams per GPU) |
| **Batch (nightly processing)** | Optimal (economic) | Overprovisioned (GPU idle 20+ hours/day) |
| **Development velocity** | Fast (local iteration) | Slow (GPU setup, debugging) |
| **Hardware lock-in** | None (any hardware works) | High (NVIDIA/CUDA specific) |
| **Infrastructure cost** | $5/day per store | $25/day per store |

**Decision**: For the batch analytics use case (process clip from yesterday, serve insights today), **CPU is the right choice**. If real-time monitoring becomes a requirement, GPUs can be added as an optional path without architectural changes (YOLOv8 supports `device="cuda"`).

---

## 6. Modular Architecture: Separation of Concerns

### Decision
Decomposed the system into **three independent subsystems**:
1. **`pipeline/`** – Computer vision processing (YOLOv8, ByteTrack, heatmap generation)
2. **`app/`** – Analytics backend (FastAPI REST API, ingestion, metrics, anomalies)
3. **`dashboard/`** – User interface (Streamlit interactive analytics)

Coupled only through **file-backed event store** (`data/events/*.json`, `data/outputs/*.mp4`).

### Rationale

#### Independent Scaling & Deployment
Each subsystem can be deployed separately:
- **Pipeline worker**: Process videos in parallel across multiple machines (no centralized coordination)
- **FastAPI backend**: Deploy as multiple replicas behind a load balancer
- **Streamlit dashboard**: Single-user app for analytics, no scaling needed

A monolith would require deploying all three components together, preventing targeted optimization.

#### Clear Ownership & Testing
Each module has:
- Explicit input/output contracts (Pydantic models, JSON schema)
- Independent test suites (no cross-service dependencies)
- Well-defined failure modes (one subsystem's failure doesn't cascade)

This enables:
- Parallel feature development (three engineers working on different subsystems)
- Isolation testing (test pipeline independently of API)
- Debugging without full system deployment

#### Technology Flexibility
Modular boundaries allow future **technology swaps** without rewriting the entire system:
- Replace FastAPI with Flask? Only `app/` changes, pipeline/dashboard unaffected.
- Swap Streamlit for a custom React dashboard? Only `dashboard/` rewritten.
- Upgrade YOLOv8 to YOLOv9? Only `pipeline/` updated.

A monolithic architecture would require more extensive refactoring.

#### Docker Containerization
Each subsystem maps to a Docker service:
```yaml
services:
  pipeline:
    image: store-intelligence:pipeline
    volumes:
      - ./data:/data  # Shared volume for videos, events, outputs
  api:
    image: store-intelligence:api
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
  dashboard:
    image: store-intelligence:dashboard
    ports:
      - "8501:8501"
    volumes:
      - ./data:/data
```

This matches production deployment requirements (Kubernetes, Docker Compose) naturally.

### Tradeoffs

| Aspect | Modular | Monolithic |
|--------|---------|-----------|
| **Code Coupling** | Low (file interface) | High (shared ORM, state) |
| **Testing Complexity** | Simpler (isolated modules) | Complex (integration tests needed) |
| **Deployment Complexity** | More services (3 containers) | Single container |
| **Data Consistency** | Eventual (file-based) | Strong (ACID transactions) |
| **Debugging** | Harder (distributed system) | Easier (single process) |
| **Latency** | Higher (file I/O) | Lower (in-memory) |

**Decision**: The file-backed event store introduces **eventual consistency** (pipeline writes events, API ingests them asynchronously). This is acceptable for batch analytics where consistency can be verified post-hoc. The architectural clarity and deployment flexibility far outweigh the added operational complexity.

### Specific Implementation

**Pipeline → Events:**
```python
# pipeline/emit.py writes JSON
with open("data/events/batch_123.json", "w") as f:
    json.dump(events, f)  # One batch per video
```

**API Ingests Events:**
```python
# app/ingestion.py
def ingest_json_file(path: str):
    with open(path) as f:
        batch = CCTVBatchEvents.model_validate_json(f.read())  # Pydantic validation
    store.add_events(batch.events)
```

**Dashboard Reads Metrics:**
```python
# dashboard/streamlit_app.py
metrics = compile_dashboard_summary()  # Queries in-memory cache populated from events
st.metric("Peak Occupancy", metrics["peak"])
```

---

## 7. Data Persistence: File-Backed Event Store

### Decision
Use **local filesystem** (`data/` directory) as the primary data persistence layer instead of a database.

### Rationale

#### Simplicity & Zero Dependencies
No PostgreSQL, Redis, or MongoDB setup required. Events are persisted as JSON files:
```
data/events/
  ├── batch_video_001.json
  ├── batch_video_002.json
  └── ...
data/outputs/
  ├── tracked_video_001.mp4
  ├── heatmap_001.png
```

This eliminates:
- Database schema migrations
- Connection pooling configuration
- Transaction management complexity
- Backup/restore procedures

#### Alignment with Batch Processing Model
The system processes videos in **discrete batches** (one batch per video file). Each batch produces:
- Tracked video (MP4)
- Detection events (JSON)
- Heatmap overlay (PNG)

A document-oriented file structure mirrors this naturally.

#### Reproducibility
All inputs and outputs are **immutable files**. Replaying analysis is trivial:
```bash
rm -rf data/events && python pipeline/run.py data/videos/  # Reprocess everything
```

With a database, ensuring reproducibility requires careful transaction isolation and query reproducibility.

#### Scalability Boundary
File-backed systems scale up to ~100K events/day (typical retail store). When reaching this boundary, migrating to a database is straightforward: add a database layer to `app/ingestion.py` without changing pipeline/dashboard.

### Tradeoffs

| Aspect | File-Backed | Database |
|--------|-------------|----------|
| **Setup Complexity** | Trivial (mkdir) | Moderate (docker run, migration) |
| **Query Flexibility** | Weak (linear scans) | Strong (indexes, joins) |
| **Concurrency Control** | Manual (file locks, locking) | Automatic (ACID transactions) |
| **Data Consistency** | Eventual | Strong (ACID) |
| **Scale Limit** | ~100K events/day | 1M+ events/day easily |
| **Backup/Recovery** | Filesystem tools | Database tools |

**Decision**: File-backed is correct for MVP/alpha stage. The simplicity benefit for a team with limited DevOps resources outweighs the query flexibility loss. At scale, adding a database layer is a planned evolution, not a rewrite.

---

## 8. Summary of Key Decisions

| Component | Choice | Rationale | Key Tradeoff |
|-----------|--------|-----------|--------------|
| **Detection** | YOLOv8 | Speed (50-100 FPS CPU) + accuracy (95 mAP) + ecosystem | Accuracy < custom models |
| **Tracking** | ByteTrack | Robustness to occlusion + zero appearance model | 5-8% ID switches vs DeepSORT's 3-5% |
| **API** | FastAPI | Type safety + Pydantic validation + async ready | Less mature than Django |
| **Dashboard** | Streamlit | Rapid iteration + Python-native + no frontend eng needed | Single-user, lower customization |
| **Compute** | CPU-first | Economic efficiency + hardware agnostic + dev velocity | Slower inference vs GPU (acceptable for batch) |
| **Architecture** | Modular (pipeline/app/dashboard) | Independent scaling, clear ownership, tech flexibility | Eventual consistency, file I/O latency |
| **Persistence** | Files (`data/`) | Zero dependencies, reproducibility, simplicity | Query flexibility limited to ~100K events/day |

---

## 9. Future Optimization Levers

### GPU Acceleration (High Impact)
**Effort**: Low (YOLOv8 supports `device="cuda"`)
**Benefit**: 5-10x throughput for real-time use cases
**Trigger**: If requirements shift to 24/7 continuous monitoring instead of batch processing

### Database Layer (Medium Complexity)
**Effort**: 2-3 weeks (add PostgreSQL, migrate ingestion logic)
**Benefit**: Query flexibility, multi-user ingestion, advanced analytics
**Trigger**: Event volume exceeds 100K/day or multi-user concurrent access needed

### Custom YOLOv8 Fine-Tuning (High Effort)
**Effort**: 4-6 weeks (data labeling, training, validation)
**Benefit**: +2-5% mAP, domain-specific optimizations (e.g., detecting employees vs customers)
**Trigger**: Retail customers report detection gaps in specific scenarios

### Appearance-Based Tracking (DeepSORT Migration) (High Effort)
**Effort**: 3-4 weeks (integrate ReID model, refactor tracking logic)
**Benefit**: Reduces ID switches to <3%, handles longer occlusions
**Trigger**: False duplicate journeys become a significant business problem

### Horizontal Scaling of Pipeline (Low Effort)
**Effort**: <1 week (add job queue, Docker orchestration)
**Benefit**: Process multiple videos in parallel across workers
**Trigger**: Batch window constraints (e.g., need 1000 clips processed in <1 hour)

---

## 10. Design Philosophy

Store Intelligence prioritizes:

1. **Pragmatism over Perfectionism**
   - MVP-ready choices (Streamlit, file persistence) over production-hardened systems (React, PostgreSQL)
   - Acceptable accuracy (95 mAP, 5-8% ID switches) over SOTA (98 mAP, 2% switches)

2. **Team Empowerment**
   - Python-first stack (no JavaScript, DevOps burden)
   - Modular architecture (parallel development)
   - Clear boundaries (independent testing and debugging)

3. **Economic Efficiency**
   - CPU-first (5x cost savings vs GPU)
   - File-backed (zero database ops)
   - Batch processing (right-sized for retail use case)

4. **Future Flexibility**
   - Each component can be upgraded independently
   - Clear abstraction boundaries (file contracts)
   - Planned evolution path documented

This philosophy enables **rapid iteration** while remaining **production-capable**. As the product matures and requirements clarify, optimization levers are available without fundamental redesign.

---

## References

- [YOLOv8 Documentation](https://docs.ultralytics.com/)
- [ByteTrack Paper](https://arxiv.org/abs/2110.06864)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [MOT Challenge Benchmark Results](https://motchallenge.net/)
