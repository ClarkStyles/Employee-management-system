"""
Handles saving alert snapshots and scheduled 48-hour cleanup.
"""
import os
import cv2
import time
import logging
import threading
import schedule
from . import config

logger = logging.getLogger(__name__)

def save_snapshot(zone_id, frame):
    """Save exactly one snapshot image per alert."""
    timestamp = int(time.time())
    filename = config.SNAPSHOT_DIR / f"{zone_id}_{timestamp}.jpg"
    cv2.imwrite(str(filename), frame)
    logger.info(f"Saved alert snapshot: {filename}")

def cleanup_snapshots():
    """Delete snapshots older than 48 hours."""
    now = time.time()
    cutoff = now - (config.SNAPSHOT_TTL_HOURS * 3600)
    count = 0
    for filename in config.SNAPSHOT_DIR.glob("*.jpg"):
        if filename.stat().st_mtime < cutoff:
            try:
                filename.unlink()
                count += 1
            except Exception as e:
                logger.error(f"Failed to delete {filename}: {e}")
    
    if count > 0:
        logger.info(f"Cleaned up {count} old snapshots")

def start_cleanup_scheduler():
    """Runs in a background thread to clean up snapshots every hour."""
    schedule.every().hour.do(cleanup_snapshots)
    
    def loop():
        while True:
            schedule.run_pending()
            time.sleep(60)
            
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    logger.info("Snapshot cleanup scheduler started")
