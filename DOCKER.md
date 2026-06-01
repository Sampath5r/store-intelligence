# Docker Deployment Guide - Store Intelligence

## Quick Start

### Prerequisites
- Docker >= 20.10
- Docker Compose >= 2.0
- 4GB RAM available
- CPU-optimized system (no GPU required)

### 5-Minute Setup

```bash
# 1. Clone and navigate to project
cd store-intelligence

# 2. Initialize data directories
mkdir -p data/videos data/events data/outputs data/logs

# 3. Copy environment configuration
cp .env.example .env

# 4. Build and start services
docker-compose build
docker-compose up -d

# 5. Verify services are running
docker-compose ps
```

**Access the services:**
- **Dashboard**: http://localhost:8501 🛍️
- **API Docs**: http://localhost:8000/docs 📚
- **API Health**: http://localhost:8000/health ✓

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Docker Compose Stack                   │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─────────────────┐          ┌─────────────────┐       │
│  │   Streamlit     │          │   FastAPI       │       │
│  │   Dashboard     │          │   Backend       │       │
│  │  :8501          │          │   :8000         │       │
│  └────────┬────────┘          └────────┬────────┘       │
│           │                            │                 │
│           │  http://api:8000           │                 │
│           └────────────────────────────┘                 │
│                     │                                    │
│        ┌────────────┴────────────┐                       │
│        │   File-Backed Store     │                       │
│        │  (Shared Data Volume)   │                       │
│        ├────────────┬────────────┤                       │
│        │            │            │                       │
│   /data/videos  /data/events  /data/outputs             │
│        │            │            │                       │
│        └────────────┴────────────┘                       │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## Service Definitions

### FastAPI Backend (`api`)
**Purpose**: REST API gateway for analytics
- **Port**: 8000 (configurable via `API_PORT`)
- **Command**: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- **Features**:
  - Hot reload for development
  - CORS enabled for dashboard access
  - Automatic event ingestion on startup
  - Health check endpoint: `/health`
  - OpenAPI docs: `/docs`
- **Volumes**:
  - `./data:/data` (shared data directory)
  - `./app:/app/app` (hot reload support)
- **Resources**: 2 CPU max, 2GB memory max

### Streamlit Dashboard (`dashboard`)
**Purpose**: Interactive analytics visualization
- **Port**: 8501 (configurable via `DASHBOARD_PORT`)
- **Command**: `streamlit run dashboard/streamlit_app.py`
- **Features**:
  - Hot reload for rapid iteration
  - Connects to FastAPI backend via `API_BASE_URL`
  - Falls back to local event store if API unavailable
  - Real-time metrics and anomaly alerts
- **Volumes**:
  - `./data:/data` (read-only data access)
  - `./dashboard:/app/dashboard` (hot reload)
  - `./app:/app/app` (shared models)
- **Resources**: 1 CPU max, 1GB memory max

### Data Volume Service (`data-volume`)
**Purpose**: Initialize and validate data directories
- **One-time initialization**: Creates required directories
- **Optional**: Run with `--profile init`
- **Directories created**:
  - `/data/videos/` - Input CCTV clips
  - `/data/events/` - Detection/tracking events (JSON)
  - `/data/outputs/` - Tracked videos and heatmaps
  - `/data/logs/` - Processing logs

---

## Environment Configuration

### Using `.env` File
```bash
# Copy template
cp .env.example .env

# Edit for your environment
nano .env

# Key variables:
API_PORT=8000                           # FastAPI port
DASHBOARD_PORT=8501                     # Streamlit port
API_BASE_URL=http://api:8000            # Dashboard → API endpoint
ENV=development                         # Environment mode
API_LOG_LEVEL=INFO                      # Logging verbosity
```

### Environment Modes

| Mode | Hot Reload | Logging | CORS | Use Case |
|------|-----------|---------|------|----------|
| `development` | Enabled | INFO | Wide-open | Local iteration |
| `staging` | Disabled | WARNING | Restricted | Pre-production testing |
| `production` | Disabled | ERROR | Tight | Production deployment |

---

## Common Commands

### Development Workflow

```bash
# Start services
docker-compose up -d

# Stream logs from all services
docker-compose logs -f

# Stream API logs only
docker-compose logs -f api

# Shell into API container for debugging
docker-compose exec api /bin/bash

# Run tests
docker-compose exec api pytest tests/ -v

# Stop services
docker-compose down

# Clean up everything (including volumes)
docker-compose down -v
```

### Using Makefile (Simplified)

```bash
# Get help on all targets
make help

# Development setup (build + start)
make dev

# Start services
make up

# Stream logs
make logs
make logs-api

# Interactive shell
make shell-api

# Check health
make health

# Clean rebuild
make rebuild

# Run tests
make test
```

---

## Volumes & Data Management

### Data Directory Structure
```
data/
├── videos/           # Input CCTV clips (MP4)
│   ├── store_cam_01.mp4
│   ├── store_cam_02.mp4
│   └── ...
├── events/          # Detection events (JSON)
│   ├── batch_001.json
│   ├── batch_002.json
│   └── ...
├── outputs/         # Processed artifacts
│   ├── tracked_001.mp4
│   ├── heatmap_001.png
│   └── ...
└── logs/            # Processing logs
    └── pipeline_run.log
```

### Volume Mounting Behavior

**API Service** (`api`):
- `./data:/data:rw` - Read/write access
- `./app:/app/app:ro` - Read-only app code (hot reload)

**Dashboard Service** (`dashboard`):
- `./data:/data:ro` - Read-only (consumes data)
- `./dashboard:/app/dashboard:ro` - Read-only components

**Why?**
- API writes events and outputs (needs write access)
- Dashboard reads for visualization (read-only is safer)
- App code in read-only mode prevents container modifications

---

## Health Checks

### Built-in Health Endpoints

**API Health**:
```bash
curl http://localhost:8000/health
# Expected response:
# {
#   "status": "healthy",
#   "services": {
#     "event_store": "ok",
#     "pipeline": "ready",
#     "cache": "initialized"
#   }
# }
```

**Docker Health Status**:
```bash
docker-compose ps
# CONTAINER            STATUS
# store-intelligence-api       Up (healthy)
# store-intelligence-dashboard Up
```

**Check service connectivity**:
```bash
# From dashboard container to API
docker-compose exec dashboard curl http://api:8000/health

# From host to API
curl http://localhost:8000/health
```

---

## Development Tips

### Hot Reload
Both services support hot reload:
- **API**: Change `app/` code → auto-restarts Uvicorn
- **Dashboard**: Change `dashboard/` code → auto-reruns Streamlit script

To disable (for testing), remove `--reload` from command.

### Debugging in Container

```bash
# Shell into API
make shell-api

# Inside container:
python -c "from app.ingestion import store; print(store.events)"
pytest tests/ -v
python -m pdb app/main.py
```

### Log Aggregation

```bash
# View last 100 lines
docker-compose logs --tail=100 api

# Follow in real-time
docker-compose logs -f api

# Timestamp from specific time
docker-compose logs --since 2024-01-15T10:00:00 api
```

### Resource Monitoring

```bash
# Real-time resource usage
docker stats

# Specific services
docker stats store-intelligence-api store-intelligence-dashboard

# Memory consumption
docker inspect store-intelligence-api | grep Memory
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] Create `.env.prod` with production settings
- [ ] Review `docker-compose.prod.yml` overrides
- [ ] Update `API_BASE_URL` to external endpoint
- [ ] Configure SSL/TLS certificates
- [ ] Set up reverse proxy (Nginx/HAProxy)
- [ ] Enable logging aggregation
- [ ] Configure monitoring (Prometheus/Datadog)

### Deployment Steps

```bash
# Build production image
docker build -t store-intelligence:latest .

# Deploy with production overrides
docker-compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d

# Verify deployment
docker-compose ps
curl https://api.example.com/health
```

### Production Configuration Changes

**Differences from development** (in `docker-compose.prod.yml`):
- Hot reload: **Disabled** (faster startup)
- Workers: **4** Uvicorn processes (parallel handling)
- Memory limits: **4GB API, 2GB Dashboard** (larger production workloads)
- Logging level: **WARNING** (reduced verbosity)
- Restart policy: **on-failure:5** (auto-recovery)
- Volume permissions: **Read-only app code** (prevent modifications)

---

## Troubleshooting

### Services won't start

```bash
# Check logs
docker-compose logs api
docker-compose logs dashboard

# Common issues:
# 1. Port already in use
#    Solution: Change API_PORT or DASHBOARD_PORT in .env

# 2. Data directory missing
#    Solution: mkdir -p data/{videos,events,outputs,logs}

# 3. Permission denied
#    Solution: chmod -R 755 data/
```

### Dashboard can't connect to API

```bash
# Check network connectivity
docker-compose exec dashboard curl http://api:8000/health

# Verify API_BASE_URL in .env
grep API_BASE_URL .env
# Should be: http://api:8000 (inside Docker network)

# Not: http://localhost:8000 (won't work from dashboard container)
```

### High memory usage

```bash
# Check memory per service
docker stats

# Reduce limits in docker-compose.yml:
# deploy.resources.limits.memory: 1G

# Or restart with resource constraints:
docker-compose up --no-start
docker-compose exec -e MEMORY_LIMIT=1G api bash
```

### Disk space issues

```bash
# Clear old containers and images
docker system prune -a

# Remove volumes (caution: deletes data)
docker-compose down -v

# Check log rotation
docker inspect store-intelligence-api | grep -A 5 LogConfig
```

---

## Performance Optimization

### CPU-First Design
- YOLOv8 nano model (3.3M params)
- No GPU dependency (CPU inference default)
- Efficient ByteTrack tracking (O(n) complexity)

**Typical Performance**:
- 30-minute video: ~5 minutes processing time (CPU)
- 50-100 detections/frame at 50 FPS
- ~500MB memory for pipeline worker

### Scaling Strategies

**Horizontal Scaling** (multiple videos in parallel):
```bash
# Run pipeline worker multiple times
for i in {1..4}; do
  docker run -v ./data:/data store-intelligence:latest \
    python pipeline/run.py data/videos/batch_$i
done
```

**Vertical Scaling** (bigger hardware):
- Increase CPU cores available to containers
- Adjust `deploy.resources.limits.cpus`
- Increase memory if processing 4K video

**GPU Acceleration** (future):
```python
# In pipeline/detect.py, change:
device = "cuda"  # instead of "cpu"
```

---

## Networking

### Internal Service Communication

Within Docker network (`store-intelligence-net`):
- API → `http://api:8000`
- Dashboard → `http://dashboard:8501`
- Services resolve via Docker DNS

### External Access

From host machine:
- API → `http://localhost:8000`
- Dashboard → `http://localhost:8501`

From custom networks:
```bash
# Connect to network
docker run -it --network store-intelligence-net python:3.10 bash

# Inside container
curl http://api:8000/health
```

---

## Cleanup

### Remove containers only (keep volumes)
```bash
docker-compose down
```

### Remove everything (including data)
```bash
docker-compose down -v
```

### Remove images
```bash
docker rmi store-intelligence:api-latest store-intelligence:dashboard-latest
```

### Deep clean
```bash
docker system prune -a
docker volume prune
```

---

## References

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Dockerfile Reference](https://docs.docker.com/engine/reference/builder/)
- [FastAPI in Docker](https://fastapi.tiangolo.com/deployment/docker/)
- [Streamlit in Docker](https://docs.streamlit.io/knowledge-base/tutorials/deploy/docker)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)

---

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review logs: `docker-compose logs -f`
3. Check `.env` configuration
4. Verify data directory exists and is writable

---

**Last Updated**: May 2026
**Version**: 1.0.0
