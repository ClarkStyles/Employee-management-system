"""
Task State Machine — manages task lifecycle transitions and timeout handling.

States: CREATED -> ASSIGNED -> ACKNOWLEDGED -> IN_PROGRESS -> COMPLETED -> CLEARED

On timeout (45s without ACK):
  - reassignment_count < 2: reassign to next best employee
  - reassignment_count >= 2: set needs_manager_attention=True, log MANAGER_FLAGGED event
"""

import logging
from django.conf import settings
from django.utils import timezone
from .models import Task, TaskEvent, Employee

logger = logging.getLogger(__name__)

# Valid state transitions
VALID_TRANSITIONS = {
    'CREATED': ['ASSIGNED', 'CLEARED'],
    'ASSIGNED': ['ACKNOWLEDGED', 'ASSIGNED', 'CLEARED'],  # ASSIGNED->ASSIGNED for reassign
    'ACKNOWLEDGED': ['IN_PROGRESS', 'COMPLETED'],
    'IN_PROGRESS': ['COMPLETED'],
    'COMPLETED': ['CLEARED'],
    'CLEARED': [],
}


def transition(task, new_status, details=None):
    """
    Transition a task to a new status.
    Validates the transition is legal, creates a TaskEvent, updates the Task.
    
    Returns:
        bool: True if transition was successful, False if invalid
    """
    details = details or {}
    old_status = task.status

    if new_status not in VALID_TRANSITIONS.get(old_status, []):
        logger.warning(
            f"Invalid transition: Task #{task.id} {old_status} → {new_status}"
        )
        return False

    task.status = new_status

    # Update timestamps based on transition
    if new_status == 'ACKNOWLEDGED':
        task.acknowledged_at = timezone.now()
    elif new_status == 'COMPLETED':
        task.completed_at = timezone.now()
        # Free the employee
        if task.assigned_employee:
            task.assigned_employee.status = 'FREE'
            task.assigned_employee.save(update_fields=['status'])

    task.save()

    TaskEvent.objects.create(
        task=task,
        event_type=new_status,
        details={**details, 'from_status': old_status},
    )

    logger.info(f"Task #{task.id}: {old_status} → {new_status}")

    # On completion, notify manager that employee is now FREE
    if new_status == 'COMPLETED' and task.assigned_employee:
        _broadcast_employee_status(
            task.assigned_employee,
            status='FREE',
            task_id=None,
            zone_id=None,
            zone_name=None,
        )

    return True


def _broadcast_employee_status(employee, status, task_id=None, zone_id=None, zone_name=None, assigned_at=None):
    """Fire-and-forget broadcast of employee_status_update to manager_updates group."""
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'manager_updates',
            {
                'type': 'employee_status_update_message',
                'employee_id': employee.id,
                'employee_name': employee.name,
                'status': status,
                'break_ends_at': None,
                'current_zone': zone_id,
                'current_zone_name': zone_name,
                'task_id': task_id,
                'assigned_at': assigned_at,
            }
        )
    except Exception as exc:
        logger.warning(f"Failed to broadcast status update for {employee.name}: {exc}")


def check_acknowledgment_timeouts():
    """
    Find tasks in ASSIGNED state that have been waiting longer than ACK_TIMEOUT_SECONDS.
    Either reassign or flag for manager attention.
    
    Returns:
        list: List of (task, action) tuples describing what was done
    """
    from .assignment import find_best_employee, create_and_assign_task

    timeout_threshold = timezone.now() - timezone.timedelta(
        seconds=settings.ACK_TIMEOUT_SECONDS
    )
    
    stale_tasks = Task.objects.filter(
        status='ASSIGNED',
        needs_manager_attention=False,
    ).select_related('assigned_employee', 'zone')

    actions = []

    for task in stale_tasks:
        # Check the last ASSIGNED event timestamp
        last_assigned_event = task.events.filter(
            event_type='ASSIGNED'
        ).order_by('-timestamp').first()

        if not last_assigned_event:
            continue
        if last_assigned_event.timestamp > timeout_threshold:
            continue

        # This task has timed out
        old_employee = task.assigned_employee

        if task.reassignment_count < settings.MAX_REASSIGNMENTS:
            # Try to reassign
            # Free the old employee
            if old_employee:
                old_employee.status = 'FREE'
                old_employee.save(update_fields=['status'])

            # Find next best employee (exclude previously assigned)
            previously_assigned_ids = list(
                task.events.filter(event_type='ASSIGNED')
                .values_list('details__employee_id', flat=True)
            )
            # Filter out None values
            previously_assigned_ids = [x for x in previously_assigned_ids if x]

            new_employee, score = find_best_employee(
                task.zone,
                exclude_ids=previously_assigned_ids,
            )

            if new_employee:
                task.assigned_employee = new_employee
                task.reassignment_count += 1
                task.save(update_fields=['assigned_employee', 'reassignment_count'])

                TaskEvent.objects.create(
                    task=task,
                    event_type='ESCALATED',
                    details={
                        'missed_employee_id': old_employee.id if old_employee else None,
                        'missed_employee_name': old_employee.name if old_employee else None,
                        'reassigned_to': new_employee.id,
                        'reassigned_to_name': new_employee.name,
                        'reassignment_count': task.reassignment_count,
                    },
                )
                TaskEvent.objects.create(
                    task=task,
                    event_type='ASSIGNED',
                    details={
                        'employee': new_employee.name,
                        'employee_id': new_employee.id,
                        'score': score,
                    },
                )

                new_employee.status = 'ASSIGNED'
                new_employee.last_assigned_at = timezone.now()
                new_employee.save(update_fields=['status', 'last_assigned_at'])

                logger.info(
                    f"Task #{task.id} reassigned: {old_employee.name if old_employee else '?'}"
                    f" → {new_employee.name} (attempt {task.reassignment_count})"
                )

                # Broadcast: old employee is now FREE
                if old_employee:
                    _broadcast_employee_status(
                        old_employee, status='FREE',
                        task_id=None, zone_id=None, zone_name=None,
                    )
                # Broadcast: new employee is now ASSIGNED
                _broadcast_employee_status(
                    new_employee, status='ASSIGNED',
                    task_id=task.id,
                    zone_id=task.zone_id,
                    zone_name=task.zone.name,
                    assigned_at=timezone.now().isoformat(),
                )

                actions.append((task, 'REASSIGNED', new_employee))
            else:
                # No available employees — flag for manager
                task.needs_manager_attention = True
                task.save(update_fields=['needs_manager_attention'])
                TaskEvent.objects.create(
                    task=task,
                    event_type='MANAGER_FLAGGED',
                    details={'reason': 'No available employees for reassignment'},
                )
                logger.warning(f"Task #{task.id} flagged: no employees available")
                actions.append((task, 'MANAGER_FLAGGED', None))
        else:
            # Max reassignments reached — flag for manager
            if old_employee:
                old_employee.status = 'FREE'
                old_employee.save(update_fields=['status'])

            task.needs_manager_attention = True
            task.save(update_fields=['needs_manager_attention'])

            TaskEvent.objects.create(
                task=task,
                event_type='MANAGER_FLAGGED',
                details={
                    'reason': f'Max reassignments ({settings.MAX_REASSIGNMENTS}) reached',
                    'reassignment_count': task.reassignment_count,
                },
            )
            logger.warning(
                f"Task #{task.id} flagged for manager: "
                f"max reassignments ({task.reassignment_count}) reached"
            )
            actions.append((task, 'MANAGER_FLAGGED', None))

    return actions


def check_break_expiry():
    """
    Find employees whose break timer has expired and return them to FREE status.
    Broadcasts employee_status_update to the manager_updates group.

    Returns:
        int: Number of employees whose breaks were expired.
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    expired = Employee.objects.filter(
        status='ON_BREAK',
        break_ends_at__lte=timezone.now(),
    )

    count = 0
    channel_layer = get_channel_layer()

    for employee in expired:
        employee.status = 'FREE'
        employee.break_ends_at = None
        employee.save(update_fields=['status', 'break_ends_at'])
        logger.info(f"Break expired: {employee.name} → FREE")

        # Notify the employee's own WS session
        async_to_sync(channel_layer.group_send)(
            f"employee_{employee.id}",
            {
                'type': 'employee_status_update_message',
                'employee_id': employee.id,
                'status': 'FREE',
                'break_ends_at': None,
            }
        )

        # Notify manager group
        async_to_sync(channel_layer.group_send)(
            'manager_updates',
            {
                'type': 'employee_status_update_message',
                'employee_id': employee.id,
                'status': 'FREE',
                'break_ends_at': None,
            }
        )
        count += 1

    return count
