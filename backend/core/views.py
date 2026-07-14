"""
DRF views for Zone, Employee, Task.
"""

import uuid
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone

from .models import Zone, Employee, Task, TaskEvent
from .serializers import (
    ZoneSerializer, EmployeeSerializer, TaskSerializer,
    ZoneStatusSerializer, TaskHistorySerializer,
)


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
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [AllowAny]

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

        # Compute aggregate metrics
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
        employee = Employee.objects.get(username=username)
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
    POST /api/auth/register/ — register a new employee account.
    Body: {username, password, name, skill_tags (optional list)}
    Returns: {token, employee_id, name, status}
    """
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()
    name = request.data.get('name', '').strip()
    skill_tags = request.data.get('skill_tags', [])

    # Validate required fields
    errors = {}
    if not username:
        errors['username'] = 'Username is required.'
    elif len(username) < 3:
        errors['username'] = 'Username must be at least 3 characters.'
    if not password:
        errors['password'] = 'Password is required.'
    elif len(password) < 6:
        errors['password'] = 'Password must be at least 6 characters.'
    if not name:
        errors['name'] = 'Display name is required.'

    if errors:
        return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)

    # Check username uniqueness
    if Employee.objects.filter(username=username).exists():
        return Response(
            {'errors': {'username': 'Username already taken.'}},
            status=status.HTTP_409_CONFLICT
        )

    # Validate skill_tags
    if not isinstance(skill_tags, list):
        skill_tags = []
    valid_skills = {'tech', 'cashier', 'greeter', 'stocking', 'customer_service'}
    skill_tags = [s for s in skill_tags if s in valid_skills]

    # Create employee
    employee = Employee(
        username=username,
        name=name,
        skill_tags=skill_tags,
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
