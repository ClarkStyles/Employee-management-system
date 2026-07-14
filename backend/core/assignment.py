"""
Assignment Engine — scores and assigns the best available employee to an alert zone.
"""

import datetime
import logging
from django.conf import settings
from django.utils import timezone
from .models import Zone, Employee, Task, TaskEvent

logger = logging.getLogger(__name__)


def score_employee(employee, alert_zone, zone_metrics=None):
    """
    Score an employee for assignment to an alert zone.
    
    score = w1*proximity + w2*zone_load + w3*skill_match
    
    - proximity: 1.0 if same zone, decreases by adjacency distance (normalized 0-1)
    - zone_load: inverse of employee's current zone density (prefer low-load zones)
    - skill_match: 1.0 if skill overlap, else 0.3 baseline
    
    Args:
        employee: Employee instance
        alert_zone: Zone instance that triggered the alert
        zone_metrics: dict of zone_id -> {density, customer_count, ...} from Redis
    
    Returns:
        float: score between 0 and 1
    """
    w1 = settings.WEIGHT_PROXIMITY
    w2 = settings.WEIGHT_ZONE_LOAD
    w3 = settings.WEIGHT_SKILL_MATCH
    zone_metrics = zone_metrics or {}

    # --- Proximity score ---
    if employee.current_zone_id == alert_zone.id:
        proximity = 1.0
    elif employee.current_zone_id is not None:
        # Look up adjacency distance
        adjacency = alert_zone.adjacency_map
        distance = adjacency.get(str(employee.current_zone_id), 5)  # default far
        # Normalize: distance 1 -> 0.8, distance 2 -> 0.6, etc.
        proximity = max(0.0, 1.0 - (distance * 0.2))
    else:
        proximity = 0.3  # No zone checked in

    # --- Zone load score ---
    if employee.current_zone_id and str(employee.current_zone_id) in zone_metrics:
        current_density = zone_metrics[str(employee.current_zone_id)].get('density', 0.5)
        # Prefer pulling from low-density zones (inverse)
        zone_load = 1.0 - min(current_density, 1.0)
    else:
        zone_load = 0.5  # Neutral if no data

    # --- Skill match score ---
    required = alert_zone.required_skill
    if required and required in employee.skill_tags:
        skill_match = 1.0
    elif not required:
        skill_match = 0.8  # No skill requirement = moderate match
    else:
        skill_match = 0.3  # Has some skills, just not the right one

    score = w1 * proximity + w2 * zone_load + w3 * skill_match
    return round(score, 4)


def find_best_employee(alert_zone, zone_metrics=None, exclude_ids=None):
    """
    Find the best available employee for an alert zone.
    
    1. Filter employees with status == FREE
    2. Score each using score_employee()
    3. Tie-break: prefer employee with oldest last_assigned_at (least recently assigned)
    4. Return (employee, score) or (None, 0)
    """
    exclude_ids = exclude_ids or []
    candidates = Employee.objects.filter(status='FREE').exclude(id__in=exclude_ids)

    if not candidates.exists():
        logger.warning(f"No FREE employees available for zone {alert_zone.name}")
        return None, 0

    scored = []
    for emp in candidates:
        score = score_employee(emp, alert_zone, zone_metrics)
        scored.append((emp, score))

    # Sort by score descending, then by last_assigned_at ascending (tie-break)
    scored.sort(key=lambda x: (
        -x[1],
        x[0].last_assigned_at or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    ))

    best_employee, best_score = scored[0]
    logger.info(
        f"Best employee for zone {alert_zone.name}: "
        f"{best_employee.name} (score={best_score})"
    )
    return best_employee, best_score


def create_and_assign_task(zone, employee, score):
    """
    Create a Task, assign it, update employee status, and return the task.
    WebSocket notification is handled by the caller.
    """
    task = Task.objects.create(
        zone=zone,
        assigned_employee=employee,
        status='ASSIGNED',
        score_at_assignment=score,
    )
    TaskEvent.objects.create(
        task=task,
        event_type='CREATED',
        details={'zone': zone.name},
    )
    TaskEvent.objects.create(
        task=task,
        event_type='ASSIGNED',
        details={
            'employee': employee.name,
            'employee_id': employee.id,
            'score': score,
        },
    )

    # Update employee status
    employee.status = 'ASSIGNED'
    employee.last_assigned_at = timezone.now()
    employee.save(update_fields=['status', 'last_assigned_at'])

    logger.info(f"Task #{task.id} created: {employee.name} → {zone.name} (score={score})")
    return task
