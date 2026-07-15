"""
WebSocket consumers for real-time employee and manager communication.
"""

import asyncio
import base64
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
      {type: "employee_status_update", employee_id, status, break_ends_at}

    Client -> Server messages:
      {type: "ack", task_id}
      {type: "complete", task_id}
      {type: "checkin", zone_id}
      {type: "start_break", duration_seconds}   # 150 or 300, only when FREE
      {type: "end_break_early"}
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
        elif msg_type == 'start_break':
            await self._handle_start_break(data)
        elif msg_type == 'end_break_early':
            await self._handle_end_break_early()
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

    async def _handle_start_break(self, data):
        """Employee requests a timed break."""
        duration = data.get('duration_seconds')
        if duration not in (150, 300):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid duration. Use 150 (2.5 min) or 300 (5 min).'
            }))
            return

        result = await self._start_break(duration)

        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': 'break_started' if result['success'] else 'break_rejected',
            'success': result['success'],
            'message': result['message'],
            'break_ends_at': result.get('break_ends_at'),
        }))

        if result['success']:
            # Broadcast to manager group
            await self.channel_layer.group_send(
                'manager_updates',
                {
                    'type': 'employee_status_update_message',
                    'employee_id': self.employee_id,
                    'status': 'ON_BREAK',
                    'break_ends_at': result.get('break_ends_at'),
                }
            )

    async def _handle_end_break_early(self):
        """Employee ends their break before timer expires."""
        result = await self._end_break()

        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': 'break_ended' if result['success'] else 'break_end_failed',
            'success': result['success'],
            'message': result['message'],
        }))

        if result['success']:
            await self.channel_layer.group_send(
                'manager_updates',
                {
                    'type': 'employee_status_update_message',
                    'employee_id': self.employee_id,
                    'status': 'FREE',
                    'break_ends_at': None,
                }
            )

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

    async def employee_status_update_message(self, event):
        """Forward status update (e.g., break expiry) to this employee client."""
        await self.send(text_data=json.dumps({
            'type': 'employee_status_update',
            'employee_id': event['employee_id'],
            'status': event['status'],
            'break_ends_at': event.get('break_ends_at'),
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

        Employee.objects.filter(id=self.employee_id).update(current_zone=zone)

        try:
            r = redis_lib.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                decode_responses=True,
            )
            for z in Zone.objects.all():
                r.srem(f"zone:{z.id}:checked_in", str(self.employee_id))
            r.sadd(f"zone:{zone_id}:checked_in", str(self.employee_id))
        except Exception as e:
            logger.error(f"Redis checkin error: {e}")

        return {
            'success': True,
            'message': f'Checked in to {zone.name}',
        }

    @database_sync_to_async
    def _start_break(self, duration_seconds):
        from core.models import Employee

        try:
            emp = Employee.objects.get(id=self.employee_id)
        except Employee.DoesNotExist:
            return {'success': False, 'message': 'Employee not found.'}

        if emp.status != 'FREE':
            return {
                'success': False,
                'message': f'Cannot start break while status is {emp.status}. Breaks only allowed when FREE.'
            }

        break_ends = timezone.now() + timezone.timedelta(seconds=duration_seconds)
        emp.status = 'ON_BREAK'
        emp.break_ends_at = break_ends
        emp.save(update_fields=['status', 'break_ends_at'])
        logger.info(f"Break started: {emp.name} ({duration_seconds}s, ends at {break_ends})")

        return {
            'success': True,
            'message': f'Break started. Returns to FREE at {break_ends.isoformat()}',
            'break_ends_at': break_ends.isoformat(),
        }

    @database_sync_to_async
    def _end_break(self):
        from core.models import Employee

        try:
            emp = Employee.objects.get(id=self.employee_id)
        except Employee.DoesNotExist:
            return {'success': False, 'message': 'Employee not found.'}

        if emp.status != 'ON_BREAK':
            return {'success': False, 'message': 'Not currently on break.'}

        emp.status = 'FREE'
        emp.break_ends_at = None
        emp.save(update_fields=['status', 'break_ends_at'])
        logger.info(f"Break ended early: {emp.name}")
        return {'success': True, 'message': 'Break ended. Welcome back!'}


class ManagerConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for manager dashboard.
    Connected to: ws/manager/

    Receives broadcasts: employee_status_update, zone_update_message
    No client -> server messages needed (read-only live feed).
    """

    async def connect(self):
        self.manager_user = self.scope.get('manager_user')

        if not self.manager_user:
            logger.warning("Manager WS rejected: not authenticated")
            await self.close(code=4401)
            return

        await self.channel_layer.group_add('manager_updates', self.channel_name)
        await self.channel_layer.group_add('zone_updates', self.channel_name)
        await self.accept()
        logger.info(f"Manager WS connected: {self.manager_user.username}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard('manager_updates', self.channel_name)
        await self.channel_layer.group_discard('zone_updates', self.channel_name)

    async def receive(self, text_data):
        # Manager dashboard is read-only; ignore client messages except ping
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except Exception:
            pass

    async def employee_status_update_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'employee_status_update',
            'employee_id': event['employee_id'],
            'status': event['status'],
            'break_ends_at': event.get('break_ends_at'),
        }))

    async def zone_update_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'zone_update',
            'zone_id': event['zone_id'],
            'zone_name': event.get('zone_name', ''),
            'state': event['state'],
            'density': event.get('density', 0),
        }))


class PreviewConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for live CV preview (manager-only).
    Connected to: ws/manager/preview/<zone_id>/

    Reads zone:{zone_id}:preview from Redis every 500ms and forwards to client.
    Sets/clears preview_active:{zone_id} in Redis using a reference counter.
    """

    FRAME_INTERVAL = 0.5  # ~2 fps

    async def connect(self):
        self.manager_user = self.scope.get('manager_user')

        if not self.manager_user:
            await self.close(code=4401)
            return

        self.zone_id = self.scope['url_route']['kwargs']['zone_id']
        self._running = True

        await self.accept()

        # Increment preview reference counter in Redis
        await self._set_preview_active(True)

        # Start frame forwarding loop
        self._loop_task = asyncio.ensure_future(self._frame_loop())
        logger.info(f"Preview WS connected: zone {self.zone_id} by {self.manager_user.username}")

    async def disconnect(self, close_code):
        self._running = False
        if hasattr(self, '_loop_task'):
            self._loop_task.cancel()
        # Decrement reference counter; stop cv_worker encoding if reaches 0
        await self._set_preview_active(False)
        logger.info(f"Preview WS disconnected: zone {self.zone_id}")

    async def receive(self, text_data):
        pass  # No client messages expected

    async def _frame_loop(self):
        """Pull frames from Redis and send to client at ~2 fps."""
        import redis as redis_lib
        from django.conf import settings

        try:
            r = redis_lib.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                decode_responses=False,  # Raw bytes for binary data
            )
        except Exception as e:
            logger.error(f"Preview Redis connect error: {e}")
            return

        last_frame = None
        while self._running:
            try:
                frame_data = r.get(f"zone:{self.zone_id}:preview")
                if frame_data and frame_data != last_frame:
                    last_frame = frame_data
                    # frame_data is already base64-encoded bytes
                    await self.send(text_data=json.dumps({
                        'type': 'preview_frame',
                        'zone_id': self.zone_id,
                        'frame': frame_data.decode('ascii'),
                    }))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Preview frame loop error: {e}")

            await asyncio.sleep(self.FRAME_INTERVAL)

    @database_sync_to_async
    def _set_preview_active(self, active: bool):
        """Increment or decrement the preview reference counter in Redis."""
        import redis as redis_lib
        from django.conf import settings

        try:
            r = redis_lib.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                decode_responses=True,
            )
            key = f"preview_active:{self.zone_id}"
            if active:
                r.incr(key)
                r.expire(key, 60)  # Safety TTL
                logger.info(f"Preview active for zone {self.zone_id}: count={r.get(key)}")
            else:
                count = r.decr(key)
                if count is not None and int(count) <= 0:
                    r.delete(key)
                    logger.info(f"Preview deactivated for zone {self.zone_id} (no more clients)")
                else:
                    logger.info(f"Preview still active for zone {self.zone_id}: count={count}")
        except Exception as e:
            logger.error(f"Redis preview_active error: {e}")
