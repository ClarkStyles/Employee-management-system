"""
WebSocket consumers for real-time employee communication.
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)


class EmployeeConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for employee sessions.
    
    Connected to: ws/employee/{token}/
    
    Server -> Client messages:
      {type: "task_offer", task_id, zone, zone_id, expires_in}
      {type: "zone_update", zone_id, zone_name, state, density}
      {type: "status_update", status, message}
    
    Client -> Server messages:
      {type: "ack", task_id}
      {type: "complete", task_id}
      {type: "checkin", zone_id}
    """

    async def connect(self):
        self.employee = self.scope.get('employee')

        if not self.employee:
            logger.warning("WebSocket connection rejected: no valid employee")
            await self.close()
            return

        self.employee_id = self.employee.id
        self.employee_group = f"employee_{self.employee_id}"

        # Join personal channel group
        await self.channel_layer.group_add(
            self.employee_group,
            self.channel_name
        )
        # Join broadcast group for zone updates
        await self.channel_layer.group_add(
            "zone_updates",
            self.channel_name
        )

        await self.accept()

        # Set employee online
        await self._set_employee_status('FREE')

        logger.info(f"WebSocket connected: {self.employee.name}")

        # Send current status
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': 'connected',
            'employee_id': self.employee_id,
            'name': self.employee.name,
            'message': f'Welcome, {self.employee.name}',
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'employee_group'):
            await self.channel_layer.group_discard(
                self.employee_group,
                self.channel_name
            )
            await self.channel_layer.group_discard(
                "zone_updates",
                self.channel_name
            )
        logger.info(
            f"WebSocket disconnected: "
            f"{self.employee.name if self.employee else 'unknown'} "
            f"(code={close_code})"
        )

    async def receive(self, text_data):
        """Handle messages from the client."""
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error', 'message': 'Invalid JSON'
            }))
            return

        msg_type = data.get('type')

        if msg_type == 'ack':
            await self._handle_ack(data)
        elif msg_type == 'complete':
            await self._handle_complete(data)
        elif msg_type == 'checkin':
            await self._handle_checkin(data)
        elif msg_type == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Unknown message type: {msg_type}'
            }))

    async def _handle_ack(self, data):
        """Employee acknowledges a task offer."""
        task_id = data.get('task_id')
        if not task_id:
            return

        result = await self._ack_task(task_id)
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': 'ack_result',
            'task_id': task_id,
            'success': result['success'],
            'message': result['message'],
            'task_status': result.get('task_status'),
        }))

    async def _handle_complete(self, data):
        """Employee marks a task as complete."""
        task_id = data.get('task_id')
        if not task_id:
            return

        result = await self._complete_task(task_id)
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': 'complete_result',
            'task_id': task_id,
            'success': result['success'],
            'message': result['message'],
        }))

        # Broadcast zone update
        if result['success'] and result.get('zone_id'):
            await self.channel_layer.group_send(
                "zone_updates",
                {
                    'type': 'zone_update_message',
                    'zone_id': result['zone_id'],
                    'zone_name': result.get('zone_name', ''),
                    'state': result.get('zone_state', 'NORMAL'),
                    'density': result.get('density', 0),
                }
            )

    async def _handle_checkin(self, data):
        """Employee checks into a zone."""
        zone_id = data.get('zone_id')
        if zone_id is None:
            return

        result = await self._checkin_to_zone(zone_id)
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': 'checkin_result',
            'zone_id': zone_id,
            'success': result['success'],
            'message': result['message'],
        }))

    # ---- Channel layer event handlers (server -> client) ----

    async def task_offer_message(self, event):
        """Receive a task offer from the channel layer and forward to client."""
        await self.send(text_data=json.dumps({
            'type': 'task_offer',
            'task_id': event['task_id'],
            'zone': event['zone_name'],
            'zone_id': event['zone_id'],
            'expires_in': event.get('expires_in', 45),
        }))

    async def zone_update_message(self, event):
        """Receive a zone update from the channel layer and forward to client."""
        await self.send(text_data=json.dumps({
            'type': 'zone_update',
            'zone_id': event['zone_id'],
            'zone_name': event.get('zone_name', ''),
            'state': event['state'],
            'density': event.get('density', 0),
        }))

    async def task_reassigned_message(self, event):
        """Notify employee that their task was reassigned away from them."""
        await self.send(text_data=json.dumps({
            'type': 'task_reassigned',
            'task_id': event['task_id'],
            'message': event.get('message', 'Task was reassigned'),
        }))

    # ---- Database operations ----

    @database_sync_to_async
    def _set_employee_status(self, status):
        from core.models import Employee
        Employee.objects.filter(id=self.employee_id).update(status=status)

    @database_sync_to_async
    def _ack_task(self, task_id):
        from core.models import Task
        from core.state_machine import transition

        try:
            task = Task.objects.get(id=task_id, assigned_employee_id=self.employee_id)
        except Task.DoesNotExist:
            return {'success': False, 'message': 'Task not found or not assigned to you'}

        if task.status != 'ASSIGNED':
            return {
                'success': False,
                'message': f'Cannot acknowledge task in {task.status} state'
            }

        # Transition ASSIGNED -> ACKNOWLEDGED
        success = transition(task, 'ACKNOWLEDGED', {'employee_id': self.employee_id})
        if success:
            # Auto-transition to IN_PROGRESS
            transition(task, 'IN_PROGRESS', {'employee_id': self.employee_id})
            return {
                'success': True,
                'message': 'Task acknowledged and in progress',
                'task_status': 'IN_PROGRESS',
            }
        return {'success': False, 'message': 'Failed to acknowledge task'}

    @database_sync_to_async
    def _complete_task(self, task_id):
        from core.models import Task, Employee
        from core.state_machine import transition

        try:
            task = Task.objects.select_related('zone').get(
                id=task_id, assigned_employee_id=self.employee_id
            )
        except Task.DoesNotExist:
            return {'success': False, 'message': 'Task not found'}

        if task.status not in ('ACKNOWLEDGED', 'IN_PROGRESS'):
            return {
                'success': False,
                'message': f'Cannot complete task in {task.status} state'
            }

        success = transition(task, 'COMPLETED', {'employee_id': self.employee_id})
        if success:
            return {
                'success': True,
                'message': 'Task completed',
                'zone_id': task.zone_id,
                'zone_name': task.zone.name,
                'zone_state': task.zone.current_state,
            }
        return {'success': False, 'message': 'Failed to complete task'}

    @database_sync_to_async
    def _checkin_to_zone(self, zone_id):
        from core.models import Employee, Zone
        import redis as redis_lib
        from django.conf import settings

        try:
            zone = Zone.objects.get(id=zone_id)
        except Zone.DoesNotExist:
            return {'success': False, 'message': 'Zone not found'}

        # Update employee's current zone
        Employee.objects.filter(id=self.employee_id).update(current_zone=zone)

        # Update Redis check-in set
        try:
            r = redis_lib.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                decode_responses=True,
            )
            # Remove from all zone check-in sets first
            for z in Zone.objects.all():
                r.srem(f"zone:{z.id}:checked_in", str(self.employee_id))
            # Add to new zone
            r.sadd(f"zone:{zone_id}:checked_in", str(self.employee_id))
        except Exception as e:
            logger.error(f"Redis checkin error: {e}")

        return {
            'success': True,
            'message': f'Checked in to {zone.name}',
        }
