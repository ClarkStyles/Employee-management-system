"""
Main entry point for cv-worker.
"""
import time
import logging
from . import config
from .capture import MultiStreamCapture
from .detector import Detector
from .zone_tracker import ZoneTracker
from .redis_publisher import RedisPublisher
from .snapshot import save_snapshot, start_cleanup_scheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting CV Worker...")
    
    # Check model existence, auto-download if missing
    import os
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
    capture = MultiStreamCapture()
    
    trackers = {zone_id: ZoneTracker(zone_id) for zone_id in config.ZONE_ROIS.keys()}
    
    start_cleanup_scheduler()
    
    logger.info("CV Pipeline running.")
    try:
        while True:
            for stream_idx, frame in capture.get_frames():
                
                # In a multi-camera setup, you'd map specific zones to specific streams.
                # For this prototype, we'll process all zones on the first stream if only 1 is active,
                # or map them if needed. We'll just run all zones on the provided frame for simplicity.
                
                for zone_id, roi in config.ZONE_ROIS.items():
                    tracker = trackers[zone_id]
                    
                    # 1. Detect
                    boxes = detector.detect(frame, roi_coords=roi)
                    
                    # 2. Get check-ins
                    checked_in = publisher.get_checked_in_employees(zone_id)
                    
                    # 3. Update State
                    state_changed = tracker.update(boxes, checked_in)
                    
                    now = time.time()
                    metrics = {
                        "zone_id": zone_id,
                        "total_person_count": tracker.current_count,
                        "checked_in_employee_ids": tracker.checked_in_employees,
                        "customer_count": tracker.customer_count,
                        "density": tracker.density,
                        "timestamp": now
                    }
                    
                    # 4. Publish Metrics
                    publisher.publish_metrics(zone_id, metrics)
                    
                    # 5. Handle Alerts
                    if state_changed:
                        publisher.publish_alert(
                            zone_id=zone_id,
                            new_state=tracker.state,
                            density=tracker.density,
                            customer_count=tracker.customer_count,
                            timestamp=now
                        )
                        if tracker.state == "ALERT":
                            save_snapshot(zone_id, frame)
                            
            # Tiny sleep to avoid pegging CPU if streams are exhausted/fast
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        capture.release()

if __name__ == "__main__":
    main()
