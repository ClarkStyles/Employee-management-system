"""
Hysteresis and zone state tracking.
"""
import time
import requests
import logging
from collections import deque
from . import config

logger = logging.getLogger(__name__)

class ZoneTracker:
    def __init__(self, zone_id):
        self.zone_id = zone_id
        self.state = "NORMAL"
        self.person_count_buffer = deque(maxlen=10) # ~2 seconds smoothing @ 5fps
        self.current_count = 0
        self.customer_count = 0
        self.checked_in_employees = []
        self.density = 0.0
        
        self.sustained_above_counter = 0
        self.sustained_below_counter = 0
        self.last_update_time = time.time()
        
        # We fetch the configuration periodically or on initialization
        self.threshold_config = {}
        self._fetch_threshold_config()
        self.last_config_fetch = time.time()

    def _fetch_threshold_config(self):
        """Fetch adaptive threshold config from backend API."""
        try:
            resp = requests.get(f"{config.API_BASE_URL}/zones/{self.zone_id}/", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                self.threshold_config = data.get('threshold_config', {})
        except Exception as e:
            logger.debug(f"Could not fetch threshold config for zone {self.zone_id}: {e}")

    def _get_current_threshold(self):
        """Look up adaptive threshold based on current time/day."""
        import datetime
        now = datetime.datetime.now()
        day_name = now.strftime("%a").lower()[:3]
        current_time = now.strftime("%H:%M")
        
        if self.threshold_config:
            for bucket in self.threshold_config.get("buckets", []):
                if day_name in bucket.get("days", []):
                    if bucket.get("start", "00:00") <= current_time < bucket.get("end", "24:00"):
                        return bucket.get("threshold", 0.5), bucket.get("customer_count", 2)
                        
            return (
                self.threshold_config.get("default_threshold", 0.5),
                self.threshold_config.get("default_customer_count", 2)
            )
        return (0.5, 2) # Fallback

    def update(self, detected_boxes, checked_in_employees):
        """
        Update the zone state with the latest detection.
        checked_in_employees: list of employee IDs currently in the zone.
        """
        now = time.time()
        dt = now - self.last_update_time
        self.last_update_time = now
        
        # Every 5 mins fetch config again
        if now - self.last_config_fetch > 300:
            self._fetch_threshold_config()
            self.last_config_fetch = now

        # Add to ring buffer for smoothing (used for alert hysteresis if needed)
        self.person_count_buffer.append(len(detected_boxes))
        
        self.current_count = len(detected_boxes)
        self.checked_in_employees = checked_in_employees
        
        # Customers = Total - Employees (floor at 0)
        self.customer_count = max(0, self.current_count - len(self.checked_in_employees))
        
        # Get threshold
        density_thresh, count_thresh = self._get_current_threshold()
        
        # Calculate density (customers / count_threshold)
        # Using min(1.0, ...) to cap at 100% or allow over 100% depending on need
        self.density = self.customer_count / count_thresh if count_thresh > 0 else 0
        
        # Hysteresis check
        is_above = self.density >= density_thresh
        
        state_changed = False
        if self.state == "NORMAL":
            if is_above:
                self.sustained_above_counter += dt
                if self.sustained_above_counter >= config.HYSTERESIS_WINDOW_SEC:
                    self.state = "ALERT"
                    state_changed = True
                    self.sustained_above_counter = 0
            else:
                self.sustained_above_counter = 0
        elif self.state == "ALERT":
            if not is_above:
                self.sustained_below_counter += dt
                if self.sustained_below_counter >= config.HYSTERESIS_WINDOW_SEC:
                    self.state = "NORMAL"
                    state_changed = True
                    self.sustained_below_counter = 0
            else:
                self.sustained_below_counter = 0
                
        return state_changed
