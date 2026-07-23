# Smart Employee Reallocation System

A real-time retail operations platform that combines computer vision, Redis-backed event streaming, and a Django/Channels backend to monitor store zones, detect crowding, and coordinate employee responses through a manager portal and employee app.

## What this project does

The system watches retail zones using a CV worker that processes camera frames or video inputs, runs YOLOv11n object detection, and publishes zone metrics and alerts. The backend uses those signals to update store state, assign tasks, and drive the manager and employee interfaces in real time.

### Core features

- Live zone monitoring from a camera, video file, URL, or YouTube link
- Person detection with YOLOv11n ONNX inference
- Zone density and state tracking with hysteresis logic
- Redis-powered real-time updates for the manager dashboard and live preview
- Employee task assignment, acknowledgement, completion, and timeout handling
- Manager portal with live CV preview and zone status views
- Snapshot capture for alert events

## Architecture

The system is composed of four main parts:

1. CV Worker (Python)
   - Reads frames from configured video sources
   - Runs detection and overlays annotations
   - Publishes metrics, alerts, and preview frames to Redis

2. Django + Channels backend
   - Exposes the REST API and ASGI WebSocket endpoints
   - Hosts the manager portal and employee app
   - Runs task state transitions, assignment logic, and timeout checks
   - Provides a customized Django Admin portal for robust backend management

3. Redis
   - Stores live metrics and preview state
   - Powers real-time event flows between the CV worker and the UI

4. Frontend (vanilla JavaScript)
   - Employee app for check-in, task handling, and status updates
   - Manager portal for zone monitoring, alerts, analytics, and live CV preview

## Tech stack

- Python 3.10+
- Django 5.x
- Django REST Framework
- Channels + Daphne
- Redis
- OpenCV
- ONNX Runtime
- YOLOv11n ONNX model

## Prerequisites

- Python 3.10 or newer
- Redis running locally on port 6379
- Optional: `yt-dlp` if you want to use YouTube video links

## Installation

1. Create and activate a virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

If you plan to use YouTube video sources, install:

```bash
pip install yt-dlp
```

3. Prepare the model

The repository expects the YOLO model at:

```text
cv_worker/models/yolo11n.onnx
```

If it is missing, run:

```bash
python scripts/download_model.py
```

4. Set up the database and seed demo data

```bash
cd backend
python manage.py migrate
python manage.py seed
```

## Running the project

### Recommended: start everything with one script

From the project root:

```bash
python scripts/run_all.py
```

This script starts:

- Redis if it is not already running
- the timeout checker
- the Redis subscriber
- the Django ASGI server on http://localhost:8000
- the CV worker

### Manual start

If you prefer to run services manually:

```bash
# Start Redis (Windows example)
redis_bin\redis-server.exe

# In a separate terminal
cd backend
python manage.py run_timeout_checker
python manage.py run_subscriber

# In another terminal
python -m daphne -b 0.0.0.0 -p 8000 backend.asgi:application

# In another terminal
python -m cv_worker.main
```

## Using the app

Open http://localhost:8000/ in your browser.

- Employee view: use seeded demo accounts such as `alice` / `demo1234` to log in and interact with tasks
- Manager portal: use the manager login flow to view zones, alerts, analytics, and live preview

## Video input configuration

The CV worker can use several input types:

- a webcam index such as `0`
- a local file path
- a URL to a stream or video
- a YouTube link

You can configure the default source in the environment or set a specific zone's `video_source` value in the admin zone page.

If no source is configured, the worker falls back to the local webcam.

## Live preview behavior

The manager preview page uses WebSocket streaming and Redis to display annotated frames from the CV worker. For preview frames to appear:

- the CV worker must be running
- Redis must be reachable on port 6379
- the manager preview page must be open for the selected zone

## Demo and simulation

You can simulate crowding for testing:

```bash
python scripts/simulate_crowd.py --zone 2 --ramp-to 15 --duration 30
```

This will trigger zone alerts and task assignment behavior in the app.

## Notes

- The current backend uses SQLite for the prototype setup.
- Snapshots are stored in the `snapshots/` directory.
- The CV worker uses the config file in `cv_worker/config.py` for detection thresholds, ROI zones, and Redis settings.
- For production, consider switching to PostgreSQL, using a proper reverse proxy, and deploying Redis separately.
