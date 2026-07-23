"""
Main entry point for cv-worker.

Run from project root:
  python -m cv_worker.main
  python cv_worker/main.py
"""
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

import time
import logging
from django.conf import settings
from cv_worker import config
from cv_worker.capture import MultiStreamCapture
from cv_worker.detector import Detector
from cv_worker.zone_tracker import ZoneTracker
from cv_worker.redis_publisher import RedisPublisher
from cv_worker.snapshot import save_snapshot, start_cleanup_scheduler
from cv_worker.preview import generate_preview

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _get_zone_sources():
    """Return a mapping of zone_id -> video source from the Django database when available."""
    try:
        import sys
        backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend')
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)
        import django
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
        django.setup()
        from core.models import Zone
        from cv_worker import config

        zones = Zone.objects.all().order_by('id')
        
        # Ensure all zones from the database have an ROI in config
        default_roi = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        for zone in zones:
            z_id_str = str(zone.id)
            if z_id_str not in config.ZONE_ROIS:
                config.ZONE_ROIS[z_id_str] = default_roi

        sources = {}
        for zone in zones:
            if zone.video_source:
                sources[str(zone.id)] = zone.video_source
        return sources
    except Exception as exc:
        logger.warning("Could not load zone video sources from Django: %s", exc)
        return {}


def main():
    logger.info("Starting CV Worker...")
    
    # Check model existence, auto-download if missing
    if not os.path.exists(config.ONNX_MODEL_PATH):
        logger.warning(f"Model not found at {config.ONNX_MODEL_PATH}. Checking for download script...")
        script_path = os.path.join(config.BASE_DIR, "scripts", "download_model.py")
        if os.path.exists(script_path):
            import subprocess
            subprocess.run(["python", script_path], cwd=config.BASE_DIR)
        else:
            logger.error("Download script not found. Please place yolo11n.onnx manually.")
            return

    publisher = RedisPublisher()
    detector = Detector()

    zone_sources = _get_zone_sources()
    if zone_sources:
        logger.info("Using zone-specific video sources: %s", zone_sources)
        capture = MultiStreamCapture(sources=list(zone_sources.values()))
    else:
        logger.info("No zone-specific video sources configured. Falling back to config.CAMERA_URLS")
        capture = MultiStreamCapture()
    
    trackers = {zone_id: ZoneTracker(zone_id) for zone_id in config.ZONE_ROIS.keys()}
    
    start_cleanup_scheduler()
    
    logger.info("CV Pipeline running.")
    try:
        frame_count = 0
        while True:
            for stream_idx, frame in capture.get_frames():
                frame_count += 1
                if frame_count % 30 == 0:
                    logger.info(f"Processed {frame_count} frames...")
                zone_id = None
                if zone_sources:
                    zone_id = list(zone_sources.keys())[stream_idx]

                for current_zone_id, roi in config.ZONE_ROIS.items():
                    if zone_id and current_zone_id != zone_id:
                        continue

                    tracker = trackers[current_zone_id]

                    # 1. Detect
                    boxes = detector.detect(frame, roi_coords=roi)

                    # 2. Get check-ins
                    checked_in = publisher.get_checked_in_employees(current_zone_id)

                    # 3. Update State
                    state_changed = tracker.update(boxes, checked_in)

                    now = time.time()
                    metrics = {
                        "zone_id": current_zone_id,
                        "total_person_count": tracker.current_count,
                        "checked_in_employee_ids": tracker.checked_in_employees,
                        "customer_count": tracker.customer_count,
                        "density": tracker.density,
                        "timestamp": now
                    }

                    # 4. Publish Metrics
                    publisher.publish_metrics(current_zone_id, metrics)

                    # 5. Handle Alerts
                    if state_changed:
                        publisher.publish_alert(
                            zone_id=current_zone_id,
                            new_state=tracker.state,
                            density=tracker.density,
                            customer_count=tracker.customer_count,
                            timestamp=now
                        )
                        if tracker.state == "ALERT":
                            save_snapshot(current_zone_id, frame)

                    # 6. Generate preview frame if manager is watching
                    generate_preview(
                        zone_id=current_zone_id,
                        frame=frame,
                        boxes=boxes,
                        roi_coords=roi,
                        customer_count=tracker.customer_count,
                        density=tracker.density,
                    )

                # Tiny sleep to yield CPU if needed without introducing artificial latency
                time.sleep(0.001)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        capture.release()

if __name__ == "__main__":
    main()
