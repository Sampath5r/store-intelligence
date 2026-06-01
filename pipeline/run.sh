#!/usr/bin/env bash
# ==============================================================================
# Purplle Store Intelligence Challenge - Batch Processing Runner
# ==============================================================================
# This script processes all CCTV videos inside data/videos/ using YOLOv8
# and ByteTrack tracking, saving tracking videos, structured event JSONs, and logs.
# ==============================================================================

# Enable strict error handling (exit on failure, block uninitialized vars)
set -eo pipefail

# Ensure wildcards expand to empty lists if no files match (prevents glob literal bugs)
shopt -s nullglob

# Define directory structures
VIDEO_DIR="data/videos"
OUT_DIR="data/outputs"
EVENT_DIR="data/events"
LOG_DIR="data/logs"

# Header Banner
echo "=============================================================================="
echo "          PURPLLE STORE INTELLIGENCE - CCTV BATCH PIPELINE RUNNER            "
echo "=============================================================================="

# Create outputs, events, and log directories if missing
mkdir -p "$OUT_DIR" "$EVENT_DIR" "$LOG_DIR"
echo "[INFO] Verified storage folders: $OUT_DIR, $EVENT_DIR, $LOG_DIR"

# Resolve the Python interpreter to use (check virtual env paths first)
if [ -f "venv/bin/python" ]; then
    PYTHON_EXEC="venv/bin/python"
    echo "[INFO] Binding to virtual environment python interpreter (POSIX)."
elif [ -f "venv/Scripts/python" ]; then
    PYTHON_EXEC="venv/Scripts/python"
    echo "[INFO] Binding to virtual environment python interpreter (Windows)."
else
    PYTHON_EXEC="python"
    echo "[WARNING] Virtual environment not detected. Falling back to system 'python'."
fi

# Locate all MP4 videos in source directory
videos=("$VIDEO_DIR"/*.mp4)

if [ ${#videos[@]} -eq 0 ]; then
    echo "[ERROR] No CCTV video files (.mp4) found in directory '$VIDEO_DIR'."
    exit 1
fi

echo "[INFO] Found ${#videos[@]} video source(s) to process."
echo "------------------------------------------------------------------------------"

start_batch_time=$(date +%s)

# Iterate through videos in batch
for video in "${videos[@]}"; do
    filename=$(basename -- "$video")
    basename="${filename%.*}"
    
    # Establish output destinations
    output_video="$OUT_DIR/${basename}_tracked.mp4"
    output_events="$EVENT_DIR/${basename}_events.json"
    log_file="$LOG_DIR/${basename}_run.log"
    
    echo "[RUNNING] Processing camera source: $filename"
    echo "  - Source Path: $video"
    echo "  - Track Video: $output_video"
    echo "  - Event Logs:  $output_events"
    echo "  - Command Log: $log_file"
    
    start_video_time=$(date +%s)
    
    # Run the unified detection & stateful tracking pipeline
    # We pipe stderr and stdout into tee to print to terminal while keeping a log file
    if $PYTHON_EXEC pipeline/detect.py \
        --video_path "$video" \
        --output_video_path "$output_video" \
        --output_metadata_path "$output_events" \
        --track 2>&1 | tee "$log_file"; then
        
        # Auto-generate movement heatmap overlaid on CCTV background frame
        heatmap_img="$OUT_DIR/${basename}_heatmap.png"
        echo "[RUNNING] Generating spatial movement heatmap for: $filename"
        if $PYTHON_EXEC pipeline/heatmap.py \
            --video_path "$video" \
            --events_path "$output_events" \
            --output_path "$heatmap_img" \
            --intensity 1.5 \
            --alpha 0.55 \
            --radius 25 >> "$log_file" 2>&1; then
            echo "  - Heatmap saved: $heatmap_img"
        else
            echo "  - [WARNING] Failed to generate heatmap overlay. See log: $log_file"
        fi
        
        end_video_time=$(date +%s)
        duration=$((end_video_time - start_video_time))
        echo "[SUCCESS] Successfully processed $filename in ${duration} seconds."
    else
        echo "[FAILED] Execution failed for $filename. Detailed error logs: $log_file"
    fi
    echo "------------------------------------------------------------------------------"
done

end_batch_time=$(date +%s)
total_duration=$((end_batch_time - start_batch_time))

# Output Summary Statistics
echo "=============================================================================="
echo "          BATCH RUN OVERVIEW - PIPELINE COMPLETE                              "
echo "  Total batch time:      ${total_duration} seconds."
echo "  Annotated tracked clips: $OUT_DIR/"
echo "  Telemetry event logs:    $EVENT_DIR/"
echo "  System process archives: $LOG_DIR/"
echo "=============================================================================="
