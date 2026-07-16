import os
import sys
import time
import json
import argparse
import redis
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

backend_dir = BASE_DIR / 'backend'
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
import django

django.setup()

from core.models import Employee, Zone


def ensure_demo_data(alert_zone_id):
    zones = list(Zone.objects.all().order_by('id'))
    if not zones:
        default_zones = [
            (1, 'Entrance', 'greeter', {'1': 1, '2': 1}),
            (2, 'Electronics', 'tech', {'1': 1, '3': 1, '4': 2}),
            (3, 'Checkout', 'cashier', {'1': 2, '2': 1, '4': 1}),
            (4, 'Grocery', '', {'2': 2, '3': 1}),
        ]
        for zone_id, name, skill, adjacency in default_zones:
            Zone.objects.get_or_create(
                id=zone_id,
                defaults={
                    'name': name,
                    'required_skill': skill,
                    'adjacency_map': adjacency,
                },
            )
        zones = list(Zone.objects.all().order_by('id'))

    if not Zone.objects.filter(id=alert_zone_id).exists():
        Zone.objects.create(
            id=alert_zone_id,
            name=f'Zone {alert_zone_id}',
            required_skill='',
            adjacency_map={},
        )

    employees = list(Employee.objects.filter(is_active=True).order_by('id'))
    if not employees:
        sample_employees = [
            ('Alice', 'alice', ['tech']),
            ('Bob', 'bob', ['cashier']),
            ('Charlie', 'charlie', ['greeter']),
            ('Diana', 'diana', ['tech', 'cashier']),
            ('Eve', 'eve', []),
            ('Frank', 'frank', []),
        ]
        for name, username, skills in sample_employees:
            employee = Employee.objects.create(
                name=name,
                username=username,
                skill_tags=skills,
                status='FREE',
                auth_token=f'{username}-token',
                is_active=True,
            )
            employee.set_password('demo1234')
            employee.save(update_fields=['password_hash'])
        employees = list(Employee.objects.filter(is_active=True).order_by('id'))

    return zones, employees


def sync_scattered_employees(alert_zone_id):
    zones, employees = ensure_demo_data(alert_zone_id)
    zone_ids = [zone.id for zone in zones]
    zone_order = [alert_zone_id] + [zone_id for zone_id in zone_ids if zone_id != alert_zone_id]
    zone_employee_ids = {zone_id: [] for zone_id in zone_order}

    for index, employee in enumerate(employees):
        target_zone_id = zone_order[index % len(zone_order)]
        target_zone = Zone.objects.get(id=target_zone_id)
        employee.current_zone = target_zone
        employee.status = 'FREE'
        employee.save(update_fields=['current_zone', 'status'])
        zone_employee_ids[target_zone_id].append(employee.id)

    return zone_employee_ids


def simulate(zone_id, ramp_to, duration):
    r = redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
        protocol=2,
    )
    
    zone_employee_ids = sync_scattered_employees(int(zone_id))
    print(f"Starting simulation for Zone {zone_id}. Ramping to {ramp_to} over {duration}s.")
    print(f"Scattered employees assigned across zones: {zone_employee_ids}")
    
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
            "checked_in_employee_ids": zone_employee_ids.get(int(zone_id), []),
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
            "checked_in_employee_ids": zone_employee_ids.get(int(zone_id), []),
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
