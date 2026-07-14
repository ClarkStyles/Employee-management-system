"""
Publishes metrics to Redis.
"""
import json
import logging
import redis
from . import config

logger = logging.getLogger(__name__)

class RedisPublisher:
    def __init__(self):
        try:
            self.r = redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                decode_responses=True
            )
            # Test connection
            self.r.ping()
            logger.info("Connected to Redis successfully.")
        except Exception as e:
            logger.error(f"Could not connect to Redis: {e}")
            self.r = None

    def get_checked_in_employees(self, zone_id):
        """Read checked-in employee IDs from Redis set."""
        if not self.r:
            return []
        try:
            return list(self.r.smembers(f"zone:{zone_id}:checked_in"))
        except Exception as e:
            logger.error(f"Redis smembers error: {e}")
            return []

    def publish_metrics(self, zone_id, metrics):
        """Write zone metrics to Redis hash."""
        if not self.r:
            return
        try:
            # We can store as a JSON string inside a single key, or as a hash
            # Using hash mapping
            self.r.hset(f"zone:{zone_id}:metrics", mapping={
                "zone_id": str(metrics["zone_id"]),
                "total_person_count": str(metrics["total_person_count"]),
                "checked_in_employee_ids": json.dumps(metrics["checked_in_employee_ids"]),
                "customer_count": str(metrics["customer_count"]),
                "density": str(metrics["density"]),
                "timestamp": str(metrics["timestamp"])
            })
        except Exception as e:
            logger.error(f"Redis hset error: {e}")

    def publish_alert(self, zone_id, new_state, density, customer_count, timestamp):
        """Publish state change to pub/sub."""
        if not self.r:
            return
        payload = {
            "zone_id": zone_id,
            "new_state": new_state,
            "density": density,
            "customer_count": customer_count,
            "timestamp": timestamp
        }
        try:
            self.r.publish("zone_alerts", json.dumps(payload))
            logger.info(f"Published alert: {payload}")
        except Exception as e:
            logger.error(f"Redis publish error: {e}")
