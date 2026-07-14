"""
Configuration for cv-worker.
"""
import os
import ast
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

# URLs or file paths for video capture
# e.g. "rtsp://192.168.1.100:554/stream1,demo_video.mp4"
_camera_urls_env = os.getenv("CAMERA_URLS", "demo_video.mp4")
CAMERA_URLS = [url.strip() for url in _camera_urls_env.split(',')]

FRAME_SAMPLE_INTERVAL = int(os.getenv("FRAME_SAMPLE_INTERVAL", "6"))
ONNX_MODEL_PATH = os.getenv("ONNX_MODEL_PATH", str(BASE_DIR / "cv_worker" / "models" / "yolo11n.onnx"))

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Simulated zones (ID matches database)
# Default regions (proportional coordinates x, y from 0 to 1) for a 1280x720 video
# For a real implementation, you'd have an API to fetch these from the DB.
ZONE_ROIS = {
    "1": [(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)],   # Entrance (top-left)
    "2": [(0.5, 0.0), (1.0, 0.0), (1.0, 0.5), (0.5, 0.5)],   # Electronics (top-right)
    "3": [(0.0, 0.5), (0.5, 0.5), (0.5, 1.0), (0.0, 1.0)],   # Checkout (bottom-left)
    "4": [(0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.5, 1.0)],   # Grocery (bottom-right)
}

HYSTERESIS_WINDOW_SEC = int(os.getenv("HYSTERESIS_WINDOW_SECONDS", 60))

SNAPSHOT_DIR = Path(os.getenv("SNAPSHOT_DIR", str(BASE_DIR / "snapshots")))
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOT_TTL_HOURS = int(os.getenv("SNAPSHOT_TTL_HOURS", 48))

# Detection tuning (runtime)
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", 0.35))
NMS_IOU_THRESHOLD = float(os.getenv("NMS_IOU_THRESHOLD", 0.45))
PERSON_CLASS_ID = int(os.getenv("PERSON_CLASS_ID", 0))

# For fetching threshold config from backend or via Redis.
# For simplicity, we'll try to use a default or fetch it via DB if we have access,
# but since this is isolated, we should ideally fetch from REST API or Redis.
# We'll use a local fallback if we can't get it.
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api")
