# Redis subscriber — listens for zone_alerts from cv-worker and triggers
# assignment engine + pushes WebSocket updates.

import json
import logging
import threading
import time
import redis as redis_lib
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

_subscriber_thread = None


def handle_zone_alert(message_data):
 # Process a zone alert message from the cv-worker.

    from core.models import Zone, Task
    from core.assignment import find_best_employee, create_and_assign_task
    from core.state_machine import transition
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    zone_id = message_data.get('zone_id')
    new_state = message_data.get('new_state')
    density = message_data.get('density', 0)

    try:
        zone = Zone.objects.get(id=zone_id)
    except Zone.DoesNotExist:
        logger.error(f"Zone {zone_id} not found")
        return

    old_state = zone.current_state
    zone.current_state = new_state
    zone.save(update_fields=['current_state'])

    channel_layer = get_channel_layer()

    if new_state == 'ALERT' and old_state != 'ALERT':
        logger.info(f"Zone {zone.name} → ALERT (density={density})")

        # Find and assign best employee
        employee, score = find_best_employee(zone)
        if employee:
            task = create_and_assign_task(zone, employee, score)

            # Send task offer via WebSocket to the specific employee
            async_to_sync(channel_layer.group_send)(
                f"employee_{employee.id}",
                {
                    'type': 'task_offer_message',
                    'task_id': task.id,
                    'zone_name': zone.name,
                    'zone_id': zone.id,
                    'expires_in': settings.ACK_TIMEOUT_SECONDS,
                }
            )

            # Notify manager dashboard: employee is now ASSIGNED
            async_to_sync(channel_layer.group_send)(
                'manager_updates',
                {
                    'type': 'employee_status_update_message',
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'status': 'ASSIGNED',
                    'break_ends_at': None,
                    'current_zone': zone.id,
                    'current_zone_name': zone.name,
                    'task_id': task.id,
                    'assigned_at': task.created_at.isoformat(),
                }
            )
        else:
            logger.warning(f"No employees available for zone {zone.name}")

    elif new_state == 'NORMAL' and old_state != 'NORMAL':
        logger.info(f"Zone {zone.name} → NORMAL")

        # Keep the assignment visible for the dashboards during the demo run.
        # Only auto-clear tasks in CREATED or ASSIGNED status if they were not just created.
        clearable_tasks = Task.objects.filter(
            zone=zone,
            status__in=['CREATED', 'ASSIGNED'],
        ).order_by('created_at')
        for task in clearable_tasks:
            if task.assigned_employee and task.assigned_employee.status in {'ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS'}:
                task.assigned_employee.status = 'FREE'
                task.assigned_employee.save(update_fields=['status'])
            transition(task, 'CLEARED', {'reason': 'Zone returned to NORMAL'})

    # Broadcast zone update to all connected clients
    async_to_sync(channel_layer.group_send)(
        "zone_updates",
        {
            'type': 'zone_update_message',
            'zone_id': zone.id,
            'zone_name': zone.name,
            'state': new_state,
            'density': density,
        }
    )


def build_redis_client():
    kwargs = {
        'host': settings.REDIS_HOST,
        'port': settings.REDIS_PORT,
        'decode_responses': True,
        'socket_connect_timeout': 2,
        'socket_timeout': 2,
    }
    try:
        return redis_lib.Redis(**kwargs, protocol=2)
    except TypeError:
        return redis_lib.Redis(**kwargs)


def start_subscriber():
    """Start listening on the Redis zone_alerts channel."""
    r = build_redis_client()
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe('zone_alerts')

    logger.info("Redis subscriber started — listening on 'zone_alerts'")

    while True:
        try:
            message = pubsub.get_message(timeout=1.0)
            if message is None:
                continue
            if message.get('type') != 'message':
                continue
            try:
                data = json.loads(message['data'])
                logger.info(f"Received zone alert payload: {data}")
                handle_zone_alert(data)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in zone_alerts: {message['data']}")
            except Exception as e:
                logger.exception(f"Error handling zone alert: {e}")
        except Exception as e:
            logger.exception(f"Redis subscriber loop failed: {e}")
            time.sleep(1)


def ensure_subscriber_thread():
    """Start the Redis subscriber in a daemon thread once per process."""
    global _subscriber_thread
    if _subscriber_thread and _subscriber_thread.is_alive():
        return _subscriber_thread

    _subscriber_thread = threading.Thread(
        target=start_subscriber,
        daemon=True,
        name='redis-zone-alert-subscriber',
    )
    _subscriber_thread.start()
    logger.info("Redis subscriber thread started")
    return _subscriber_thread


def start_subscriber_thread():
    """Backward-compatible wrapper for starting the Redis subscriber thread."""
    return ensure_subscriber_thread()


class Command(BaseCommand):
    help = 'Run the Redis zone_alerts subscriber'

    def handle(self, *args, **options):
        self.stdout.write('Starting Redis subscriber...')
        start_subscriber()
