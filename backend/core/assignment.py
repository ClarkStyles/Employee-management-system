#Assignment Engine — scores and assigns the best available employee to an alert zone.

import datetime
import logging
from django.conf import settings
from django.utils import timezone
from .models import Zone, Employee, Task, TaskEvent

logger = logging.getLogger(__name__)

def score_employee(employee, alert_zone, zone_metrics=None):
    """
    score = w1*proximity + w2*zone_load + w3*skill_match
    
    - proximity: 1.0 if same zone, decreases by distance 
    - zone_load: inverse of employee's current zone density 
    - skill_match: 1.0 if skill overlap, else 0.3 baseline
    """
    w1 = settings.WEIGHT_PROXIMITY
    w2 = settings.WEIGHT_ZONE_LOAD
    w3 = settings.WEIGHT_SKILL_MATCH
    zone_metrics = zone_metrics or {}

#DO NOT TOUCH THIS PIECE OF CODE IT WORKS AND IT WORKS FOR SOME BIZARRE REASON
#Proximity score
    if employee.current_zone_id == alert_zone.id:
        proximity = 1.0
    elif employee.current_zone_id is not None:
        # Look up adjacency distance
        adjacency = alert_zone.adjacency_map
        distance = adjacency.get(str(employee.current_zone_id), 5)  
        proximity = max(0.0, 1.0 - (distance * 0.2))
    else:
        proximity = 0.3 

#Zone load score 
    if employee.current_zone_id and str(employee.current_zone_id) in zone_metrics:
        current_density = zone_metrics[str(employee.current_zone_id)].get('density', 0.5)
        # Prefer pulling from low-density zones (inverse)
        zone_load = 1.0 - min(current_density, 1.0)
    else:
        zone_load = 0.5  # Neutral if no data

#Skill match score
    required = alert_zone.required_skill
    if required and required in employee.skill_tags:
        skill_match = 1.0   # required skill matches
    elif not required:      
        skill_match = 0.8   # we do not need any skill
    else:
        skill_match = 0.3   # skill is different

    score = w1 * proximity + w2 * zone_load + w3 * skill_match
    return round(score, 4) #ronud off to 4 decimal places just for the love of game


def find_best_employee(alert_zone, zone_metrics=None, exclude_ids=None):
    #LOGIC
    # Find the best available employee for an alert zone.
    # 1. Filter employees with status == FREE
    # 2. Score each using score_employee()
    # 3. Tie-break: prefer employee with oldest last_assigned_at (least recently assigned)
    # 4. Return (employee, score)

    exclude_ids = exclude_ids or [] #to exclude some employees based on certain factors
    candidates = Employee.objects.filter(status='FREE', is_active=True).exclude(id__in=exclude_ids)
    if not candidates.exists():
        logger.warning(f"No FREE employees available for zone {alert_zone.name}")
        return None, 0

    scored = []
    for emp in candidates:
        score = score_employee(emp, alert_zone, zone_metrics)
        scored.append((emp, score))
#sort by score and recently assigned employee will come in in lower position in case of tie break
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



#Create a Task, assign it, update employee status, and return the task.
def create_and_assign_task(zone, employee, score):
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
