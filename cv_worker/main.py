"""
Main entry point for cv-worker.
"""
import os
import time
import logging
from django.conf import settings
from . import config
from .capture import MultiStreamCapture
from .detector import Detector
from .zone_tracker import ZoneTracker
from .redis_publisher import RedisPublisher
from .snapshot import save_snapshot, start_cleanup_scheduler
from .preview import generate_preview

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _get_zone_sources():
    """Return a mapping of zone_id -> video source from the Django database when available."""
    try:
        import django
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
        django.setup()
        from backend.core.models import Zone

        zones = Zone.objects.all().order_by('id')
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
        while True:
            for stream_idx, frame in capture.get_frames():
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

                # Tiny sleep to avoid pegging CPU if streams are exhausted/fast
                time.sleep(0.01)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        capture.release()

if __name__ == "__main__":
    main()
