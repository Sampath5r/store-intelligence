# STORE INTELLIGENCE - STEP-BY-STEP EXECUTION GUIDE

## ALL COMMANDS ARE EXECUTED IN: c:\Users\revur\Desktop\store-intelligence

---

## SECTION 1: INITIAL SETUP

### Step 1.1 - Activate Virtual Environment
**Location:** c:\Users\revur\Desktop\store-intelligence
```
.\venv\Scripts\Activate.ps1
```
**Expected:** Prompt changes to show (venv)

### Step 1.2 - Verify Python Version
**Location:** c:\Users\revur\Desktop\store-intelligence
```
python --version
```
**Expected:** Python 3.12.10

### Step 1.3 - Install All Requirements
**Location:** c:\Users\revur\Desktop\store-intelligence
```
pip install -r requirements.txt --upgrade
```
**Expected:** All packages installed successfully

### Step 1.4 - Verify Key Packages
**Location:** c:\Users\revur\Desktop\store-intelligence
```
pip list | Select-String "ultralytics|fastapi|streamlit"
```
**Expected:** Shows ultralytics, fastapi, streamlit versions

---

## SECTION 2: DATA DIRECTORY SETUP

### Step 2.1 - Create Data Directories
**Location:** c:\Users\revur\Desktop\store-intelligence
```
New-Item -ItemType Directory -Path data\videos -Force
New-Item -ItemType Directory -Path data\events -Force
New-Item -ItemType Directory -Path data\outputs -Force
New-Item -ItemType Directory -Path data\logs -Force
```

### Step 2.2 - Verify Directories Created
**Location:** c:\Users\revur\Desktop\store-intelligence
```
Get-ChildItem -Path data\ -Directory
```
**Expected Output:**
```
Mode   Name
----   ----
d----  events
d----  logs
d----  outputs
d----  videos
```

### Step 2.3 - Add Test Videos (Optional)
Copy your MP4 video files to: `data\videos\`
```
Example: data\videos\billing_camera.mp4
Example: data\videos\entry_camera.mp4
Example: data\videos\floor_camera.mp4
```

---

## SECTION 3: RUNNING COMPONENTS (CHOOSE ONE OR MORE)

### Option A: Run FastAPI Backend

**Location:** c:\Users\revur\Desktop\store-intelligence
**Terminal:** Open new terminal (Terminal 1)

```
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Expected Output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

**Test API (in another terminal):**
```
curl http://localhost:8000/health
curl http://localhost:8000/docs
```

---

### Option B: Run Streamlit Dashboard

**Location:** c:\Users\revur\Desktop\store-intelligence
**Terminal:** Open new terminal (Terminal 2)

```
.\venv\Scripts\Activate.ps1
streamlit run dashboard/streamlit_app.py
```

**Expected Output:**
```
You can now view your Streamlit app in your browser.
Local URL: http://localhost:8501
```

**Access:** Open http://localhost:8501 in browser

---

### Option C: Run Detection Pipeline

**Location:** c:\Users\revur\Desktop\store-intelligence
**Terminal:** Open new terminal (Terminal 3)

**Prerequisite:** Add test video to `data\videos\test.mp4`

```
.\venv\Scripts\Activate.ps1
python pipeline/detect.py --video_path data/videos/test.mp4 --track
```

**Parameters:**
- `--video_path` : Path to input video file
- `--track` : Enable ByteTrack tracking
- `--conf` : Confidence threshold (default: 0.5)
- `--model_path` : YOLOv8 model path (default: yolov8n.pt)

**Output Files Generated:**
```
data/outputs/test_output.mp4          ← Processed video with detections
data/events/test_events.json          ← Event/telemetry data
```

---

### Option D: Run Tests

**Location:** c:\Users\revur\Desktop\store-intelligence

```
.\venv\Scripts\Activate.ps1
python -m pytest tests/ -v
```

**Run Specific Test:**
```
python -m pytest tests/test_models.py -v
python -m pytest tests/test_metrics.py -v
python -m pytest tests/test_pipeline.py -v
```

---

## SECTION 4: DOCKER DEPLOYMENT

### Step 4.1 - Start All Services (Docker)

**Location:** c:\Users\revur\Desktop\store-intelligence

```
docker-compose up -d
```

**Starts:**
- FastAPI on port 8000
- Streamlit Dashboard on port 8501

### Step 4.2 - Check Service Status

**Location:** c:\Users\revur\Desktop\store-intelligence

```
docker-compose ps
```

**Expected Output:**
```
STATUS: Up (healthy)
```

### Step 4.3 - View Logs

**Location:** c:\Users\revur\Desktop\store-intelligence

```
docker-compose logs -f api
docker-compose logs -f dashboard
```

### Step 4.4 - Stop Services

**Location:** c:\Users\revur\Desktop\store-intelligence

```
docker-compose down
```

### Step 4.5 - Production Mode

**Location:** c:\Users\revur\Desktop\store-intelligence

```
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## SECTION 5: BATCH VIDEO PROCESSING

**Location:** c:\Users\revur\Desktop\store-intelligence

Process multiple videos automatically:

```
.\venv\Scripts\Activate.ps1

python pipeline/detect.py --video_path data/videos/camera1.mp4 --track
python pipeline/detect.py --video_path data/videos/camera2.mp4 --track
python pipeline/detect.py --video_path data/videos/camera3.mp4 --track
python pipeline/detect.py --video_path data/videos/camera4.mp4 --track
python pipeline/detect.py --video_path data/videos/camera5.mp4 --track
```

**Output Files Generated:**
```
data/outputs/camera1_output.mp4          data/events/camera1_events.json
data/outputs/camera2_output.mp4          data/events/camera2_events.json
data/outputs/camera3_output.mp4          data/events/camera3_events.json
data/outputs/camera4_output.mp4          data/events/camera4_events.json
data/outputs/camera5_output.mp4          data/events/camera5_events.json
```

---

## SECTION 6: COMPLETE WORKFLOWS

### WORKFLOW 1: DEVELOPMENT MODE (3 Terminals)

**All locations:** c:\Users\revur\Desktop\store-intelligence

**Terminal 1 - FastAPI Backend:**
```
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 - Streamlit Dashboard:**
```
.\venv\Scripts\Activate.ps1
streamlit run dashboard/streamlit_app.py
```

**Terminal 3 - Run Pipeline on Videos:**
```
.\venv\Scripts\Activate.ps1
python pipeline/detect.py --video_path data/videos/test1.mp4 --track
python pipeline/detect.py --video_path data/videos/test2.mp4 --track
```

**Access Points:**
- API: http://localhost:8000
- Dashboard: http://localhost:8501
- API Docs: http://localhost:8000/docs

---

### WORKFLOW 2: DOCKER DEPLOYMENT (Single Command)

**Location:** c:\Users\revur\Desktop\store-intelligence

```
docker-compose up -d
```

**Services Automatically Start:**
- FastAPI on http://localhost:8000
- Dashboard on http://localhost:8501
- Auto-ingests events from data/events/

**Check Status:**
```
docker-compose ps
```

---

## SECTION 7: API TESTING

**Location:** Run in a separate terminal while API is running

### Test 1: Health Check
```
curl http://localhost:8000/health
```

### Test 2: Get Metrics
```
curl http://localhost:8000/metrics
```

### Test 3: Get All Detections
```
curl http://localhost:8000/detections
```

### Test 4: Get Anomalies
```
curl http://localhost:8000/anomalies
```

### Test 5: Interactive API Explorer
Open in browser: http://localhost:8000/docs

---

## SECTION 8: OUTPUT FILES & LOCATIONS

### Input Locations:
```
data/videos/
  ├── billing_camera.mp4
  ├── entry_camera.mp4
  ├── floor_camera.mp4
  └── ...
```

### Output Locations After Processing:

**Processed Videos:**
```
data/outputs/
  ├── billing_camera_output.mp4
  ├── entry_camera_output.mp4
  ├── floor_camera_output.mp4
  └── {video_name}_output.mp4
```

**Event Data:**
```
data/events/
  ├── billing_camera_events.json
  ├── entry_camera_events.json
  ├── floor_camera_events.json
  └── {video_name}_events.json
```

**Logs:**
```
data/logs/
  └── application logs
```

---

## SECTION 9: QUICK COMMANDS REFERENCE

### Setup & Run Backend:
```
cd c:\Users\revur\Desktop\store-intelligence
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

### Setup & Run Dashboard:
```
cd c:\Users\revur\Desktop\store-intelligence
.\venv\Scripts\Activate.ps1
streamlit run dashboard/streamlit_app.py
```

### Process Single Video:
```
cd c:\Users\revur\Desktop\store-intelligence
.\venv\Scripts\Activate.ps1
python pipeline/detect.py --video_path data/videos/test.mp4 --track
```

### Run Tests:
```
cd c:\Users\revur\Desktop\store-intelligence
.\venv\Scripts\Activate.ps1
python -m pytest tests/ -v
```

### Start Docker Services:
```
cd c:\Users\revur\Desktop\store-intelligence
docker-compose up -d
```

### Stop Docker Services:
```
cd c:\Users\revur\Desktop\store-intelligence
docker-compose down
```

---

## SECTION 10: TROUBLESHOOTING

### Issue: Virtual environment not activating
**Solution:**
```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
```

### Issue: ModuleNotFoundError
**Solution:**
```
pip install -r requirements.txt --upgrade
```

### Issue: Port 8000 already in use
**Solution:**
```
netstat -ano | Select-String ":8000"
taskkill /PID <PID> /F
```

### Issue: Docker services won't start
**Solution:**
```
docker-compose down -v
docker-compose up -d --build
```

### Issue: Video file not found
**Solution:** Ensure video files are in `data/videos/` directory

### Issue: No events being generated
**Solution:** Check that the video file is readable and has proper format

---

## SUMMARY

**All commands run from:** `c:\Users\revur\Desktop\store-intelligence`

**Quick Start Options:**
1. API Only: `python -m uvicorn app.main:app --reload`
2. Dashboard Only: `streamlit run dashboard/streamlit_app.py`
3. Process Videos: `python pipeline/detect.py --video_path data/videos/test.mp4 --track`
4. Docker (Everything): `docker-compose up -d`
5. Tests: `python -m pytest tests/ -v`

**Access Points (When Running):**
- FastAPI: http://localhost:8000
- Dashboard: http://localhost:8501
- API Docs: http://localhost:8000/docs

✅ Ready to execute! Choose a workflow from Section 5 or 6 above.
