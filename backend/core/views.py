"""
DRF views for Zone, Employee, Task, and Manager operations.
"""

import uuid
import logging
from datetime import timedelta

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token

from .models import Zone, Employee, Task, TaskEvent
from .middleware import IsManagerPermission
from .serializers import (
    ZoneSerializer, EmployeeSerializer, TaskSerializer,
    ZoneStatusSerializer, TaskHistorySerializer, EmployeeStatsSerializer,
)

logger = logging.getLogger(__name__)


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'], url_path='status')
    def zone_status(self, request):
        """GET /api/zones/status/ — current state of all zones for manager dashboard."""
        zones = Zone.objects.all()
        serializer = ZoneStatusSerializer(zones, many=True)
        return Response(serializer.data)


class EmployeeViewSet(viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        """Only return active employees by default."""
        return Employee.objects.filter(is_active=True)

    def create(self, request, *args, **kwargs):
        """
        POST /api/employees/ — manager-only.
        Creates an employee with optional manager-provided username and password.
        """
        if not IsManagerPermission().has_permission(request, self):
            return Response({'error': 'Manager authentication required.'}, status=status.HTTP_403_FORBIDDEN)

        name = request.data.get('name', '').strip()
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip()
        skill_tags = request.data.get('skill_tags', [])
        default_zone_id = request.data.get('default_zone', None)

        if not name:
            return Response({'error': 'Name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if not username:
            return Response({'error': 'Username is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(username) < 3:
            return Response({'error': 'Username must be at least 3 characters.'}, status=status.HTTP_400_BAD_REQUEST)
        if Employee.objects.filter(username=username).exists():
            return Response({'error': 'Username already taken.'}, status=status.HTTP_409_CONFLICT)

        if not password:
            return Response({'error': 'Password is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(password) < 4:
            return Response({'error': 'Password must be at least 4 characters.'}, status=status.HTTP_400_BAD_REQUEST)

        employee = Employee(
            name=name,
            username=username,
            skill_tags=skill_tags if isinstance(skill_tags, list) else [],
            status='OFFLINE',
            auth_token=uuid.uuid4().hex,
            is_active=True,
        )
        employee.set_password(password)

        if default_zone_id:
            try:
                zone = Zone.objects.get(id=default_zone_id)
                employee.current_zone = zone
            except Zone.DoesNotExist:
                pass

        employee.save()

        logger.info(f"Manager created employee: {employee.name} (username={username})")
        response_data = {
            'employee_id': employee.id,
            'name': employee.name,
            'username': username,
            'auth_token': employee.auth_token,
            'status': employee.status,
        }
        return Response(response_data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """
        DELETE /api/employees/{id}/ — manager-only soft delete.
        Returns 409 if employee has an active task, unless ?force=true.
        """
        if not IsManagerPermission().has_permission(request, self):
            return Response({'error': 'Manager authentication required.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            employee = Employee.objects.get(pk=kwargs['pk'])
        except Employee.DoesNotExist:
            return Response({'error': 'Employee not found.'}, status=status.HTTP_404_NOT_FOUND)

        force = request.query_params.get('force', '').lower() == 'true'

        # Check for active tasks
        active_task = Task.objects.filter(
            assigned_employee=employee,
            status__in=['ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS'],
        ).first()

        if active_task and not force:
            return Response({
                'error': 'Employee has an active task. Use ?force=true to override.',
                'active_task_id': active_task.id,
                'task_status': active_task.status,
                'zone': active_task.zone.name,
            }, status=status.HTTP_409_CONFLICT)

        if active_task and force:
            # Log a removal event and free the task
            TaskEvent.objects.create(
                task=active_task,
                event_type='MANAGER_REMOVED',
                details={
                    'reason': 'Employee removed by manager (force)',
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                },
            )
            active_task.status = 'CLEARED'
            active_task.assigned_employee = None
            active_task.save(update_fields=['status', 'assigned_employee'])
            logger.warning(f"Force-removed employee {employee.name}: task #{active_task.id} cleared.")

        # Soft delete
        employee.is_active = False
        employee.status = 'OFFLINE'
        employee.save(update_fields=['is_active', 'status'])
        logger.info(f"Employee soft-deleted: {employee.name} (id={employee.id})")
        return Response({'success': True, 'message': f'{employee.name} removed.'})

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        """GET /api/employees/me/ — get current employee by token."""
        token = request.headers.get('Authorization', '').replace('Token ', '')
        try:
            employee = Employee.objects.get(auth_token=token)
            serializer = self.get_serializer(employee)
            return Response(serializer.data)
        except Employee.DoesNotExist:
            return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'], url_path='history')
    def task_history(self, request):
        """GET /api/tasks/history/ — completed tasks with timing metrics."""
        tasks = Task.objects.filter(
            status__in=['COMPLETED', 'CLEARED']
        ).select_related('assigned_employee', 'zone').order_by('-completed_at')[:100]
        serializer = TaskHistorySerializer(tasks, many=True)

        response_times = [
            (t.acknowledged_at - t.created_at).total_seconds()
            for t in tasks if t.acknowledged_at
        ]
        resolution_times = [
            (t.completed_at - t.created_at).total_seconds()
            for t in tasks if t.completed_at
        ]

        data = {
            'tasks': serializer.data,
            'metrics': {
                'total_completed': len(tasks),
                'avg_response_time': (
                    sum(response_times) / len(response_times)
                    if response_times else None
                ),
                'avg_resolution_time': (
                    sum(resolution_times) / len(resolution_times)
                    if resolution_times else None
                ),
                'tasks_today': Task.objects.filter(
                    created_at__date=timezone.now().date()
                ).count(),
            }
        }
        return Response(data)

    @action(detail=False, methods=['get'], url_path='active')
    def active_tasks(self, request):
        """GET /api/tasks/active/ — tasks not completed or cleared."""
        tasks = Task.objects.exclude(
            status__in=['COMPLETED', 'CLEARED']
        ).select_related('assigned_employee', 'zone')
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Employee authentication (employee-facing)
# ---------------------------------------------------------------------------

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def auth_token(request):
    """
    POST /api/auth/token/ — employee login with username + password.
    Returns the session token on success.
    """
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()

    if not username or not password:
        return Response(
            {'error': 'Username and password are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        employee = Employee.objects.get(username=username, is_active=True)
    except Employee.DoesNotExist:
        return Response(
            {'error': 'Invalid username or password.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if not employee.check_password(password):
        return Response(
            {'error': 'Invalid username or password.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Regenerate token on every login for session security
    employee.auth_token = uuid.uuid4().hex
    employee.status = 'FREE'
    employee.save(update_fields=['auth_token', 'status'])

    return Response({
        'token': employee.auth_token,
        'employee_id': employee.id,
        'name': employee.name,
        'status': employee.status,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def register_employee(request):
    """
    POST /api/auth/register/ — now manager-only employee provisioning.
    Kept for backward compatibility; use POST /api/employees/ instead.
    """
    if not IsManagerPermission().has_permission(request, None):
        return Response(
            {'error': 'Employee self-registration is disabled. Contact your manager.'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Same logic as EmployeeViewSet.create for direct API usage
    name = request.data.get('name', '').strip()
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()
    skill_tags = request.data.get('skill_tags', [])

    errors = {}
    if not name:
        errors['name'] = 'Name is required.'
    if not username or len(username) < 3:
        errors['username'] = 'Username must be at least 3 characters.'
    if not password or len(password) < 4:
        errors['password'] = 'Password must be at least 4 characters.'

    if errors:
        return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)

    if Employee.objects.filter(username=username).exists():
        return Response(
            {'errors': {'username': 'Username already taken.'}},
            status=status.HTTP_409_CONFLICT
        )

    employee = Employee(
        username=username,
        name=name,
        skill_tags=skill_tags if isinstance(skill_tags, list) else [],
        status='FREE',
        auth_token=uuid.uuid4().hex,
    )
    employee.set_password(password)
    employee.save()

    return Response({
        'token': employee.auth_token,
        'employee_id': employee.id,
        'name': employee.name,
        'status': employee.status,
    }, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Manager authentication (session-based, separate from employee token auth)
# ---------------------------------------------------------------------------

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def manager_login(request):
    """
    POST /api/auth/manager/login/ — manager login (Django session).
    Body: {username, password}
    """
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()

    if not username or not password:
        return Response({'error': 'Username and password required.'}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({'error': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_staff:
        return Response({'error': 'Manager access required.'}, status=status.HTTP_403_FORBIDDEN)

    if not user.is_active:
        return Response({'error': 'Account disabled.'}, status=status.HTTP_403_FORBIDDEN)

    login(request, user)
    # Also set CSRF token so the SPA can make POST requests
    csrf_token = get_token(request)
    return Response({
        'username': user.username,
        'display_name': user.get_full_name() or user.username,
        'csrftoken': csrf_token,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def manager_logout(request):
    """POST /api/auth/manager/logout/ — destroy manager session."""
    logout(request)
    return Response({'success': True})


@api_view(['GET'])
@permission_classes([AllowAny])
def manager_me(request):
    """GET /api/auth/manager/me/ — check if manager is logged in."""
    user = request.user
    if hasattr(user, 'is_staff') and user.is_staff and user.is_active:
        return Response({
            'authenticated': True,
            'username': user.username,
            'display_name': user.get_full_name() or user.username,
            'csrftoken': get_token(request),
        })
    return Response({'authenticated': False}, status=status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([AllowAny])
def employee_stats(request):
    """
    GET /api/dashboard/employee_stats?range=today|7d  (manager only)

    Returns per-employee:
      - acknowledged count
      - missed count (ESCALATED events where details.missed_employee_id == employee.id)
      - ack_rate
      - current status + break_ends_at
    """
    if not IsManagerPermission().has_permission(request, None):
        return Response({'error': 'Manager authentication required.'}, status=status.HTTP_403_FORBIDDEN)

    range_param = request.query_params.get('range', 'today')
    now = timezone.now()
    if range_param == '7d':
        since = now - timedelta(days=7)
    else:
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)

    employees = Employee.objects.filter(is_active=True)
    results = []

    for emp in employees:
        # Acknowledged: ACKNOWLEDGED TaskEvents on tasks assigned to this employee
        ack_count = TaskEvent.objects.filter(
            event_type='ACKNOWLEDGED',
            timestamp__gte=since,
            task__assigned_employee=emp,
        ).count()

        # Missed: ESCALATED events where details.missed_employee_id == emp.id
        missed_count = TaskEvent.objects.filter(
            event_type='ESCALATED',
            timestamp__gte=since,
            details__missed_employee_id=emp.id,
        ).count()

        total = ack_count + missed_count
        ack_rate = round(ack_count / total, 3) if total > 0 else None

        results.append({
            'employee_id': emp.id,
            'name': emp.name,
            'status': emp.status,
            'break_ends_at': emp.break_ends_at.isoformat() if emp.break_ends_at else None,
            'acknowledged': ack_count,
            'missed': missed_count,
            'ack_rate': ack_rate,
        })

    # Sort by missed count descending, then name
    results.sort(key=lambda x: (-x['missed'], x['name']))

    total_employees = employees.count()
    online_count = employees.exclude(status__in=['OFFLINE', 'ON_BREAK']).count()
    on_break_count = employees.filter(status='ON_BREAK').count()

    return Response({
        'range': range_param,
        'since': since.isoformat(),
        'summary': {
            'total_employees': total_employees,
            'online': online_count,
            'on_break': on_break_count,
        },
        'employees': results,
    })
