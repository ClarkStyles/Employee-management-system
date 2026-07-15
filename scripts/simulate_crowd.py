import os
import time
import json
import argparse
import redis
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

def simulate(zone_id, ramp_to, duration):
    r = redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True
    )
    
    print(f"Starting simulation for Zone {zone_id}. Ramping to {ramp_to} over {duration}s.")
    
    # 1. Ramp up
    steps = 10
    step_time = duration / 2 / steps
    
    threshold = 0.7
    capacity = 8 # Default from config
    
    current_count = 0
    state = "NORMAL"
    
    for i in range(steps):
        current_count = int((i + 1) / steps * ramp_to)
        density = current_count / capacity
        
        metrics = {
            "zone_id": zone_id,
            "total_person_count": current_count,
            "checked_in_employee_ids": [],
            "customer_count": current_count,
            "density": density,
            "timestamp": time.time()
        }
        r.hset(f"zone:{zone_id}:metrics", mapping={
            k: (json.dumps(v) if isinstance(v, list) else str(v)) for k,v in metrics.items()
        })
        
        if density >= threshold and state == "NORMAL":
            print(f"Zone {zone_id} crossing ALERT threshold...")
            # We skip the 60s hysteresis for the fast simulation
            state = "ALERT"
            payload = {
                "zone_id": zone_id,
                "new_state": state,
                "density": density,
                "customer_count": current_count,
                "timestamp": time.time()
            }
            r.publish("zone_alerts", json.dumps(payload))
            print(f"Published ALERT for Zone {zone_id}")
            
        time.sleep(step_time)
        
    print(f"Holding peak for 10 seconds...")
    time.sleep(10)
    
    # 2. Ramp down
    for i in range(steps, -1, -1):
        current_count = int(i / steps * ramp_to)
        density = current_count / capacity
        
        metrics = {
            "zone_id": zone_id,
            "total_person_count": current_count,
            "checked_in_employee_ids": [],
            "customer_count": current_count,
            "density": density,
            "timestamp": time.time()
        }
        r.hset(f"zone:{zone_id}:metrics", mapping={
            k: (json.dumps(v) if isinstance(v, list) else str(v)) for k,v in metrics.items()
        })
        
        if density < threshold and state == "ALERT":
            print(f"Zone {zone_id} dropping below threshold...")
            state = "NORMAL"
            payload = {
                "zone_id": zone_id,
                "new_state": state,
                "density": density,
                "customer_count": current_count,
                "timestamp": time.time()
            }
            r.publish("zone_alerts", json.dumps(payload))
            print(f"Published NORMAL for Zone {zone_id}")
            
        time.sleep(step_time)

    print("Simulation complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone", type=str, default="2", help="Zone ID (default: 2 - Electronics). Use backend seed IDs 1-4 for demo mode.")
    parser.add_argument("--ramp-to", type=int, default=15, help="Peak person count")
    parser.add_argument("--duration", type=int, default=20, help="Total duration in seconds")
    args = parser.parse_args()
    
    simulate(args.zone, args.ramp_to, args.duration)
