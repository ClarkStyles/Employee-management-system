"""
DRF serializers for Zone, Employee, Task, TaskEvent.
"""

from rest_framework import serializers
from .models import Zone, Employee, Task, TaskEvent


class ZoneSerializer(serializers.ModelSerializer):
    current_threshold = serializers.SerializerMethodField()
    employee_count = serializers.SerializerMethodField()

    class Meta:
        model = Zone
        fields = [
            'id', 'name', 'threshold_config', 'hysteresis_window',
            'current_state', 'required_skill', 'adjacency_map',
            'current_threshold', 'employee_count', 'created_at',
        ]

    def get_current_threshold(self, obj):
        density, customer_count = obj.get_current_threshold()
        return {'density': density, 'customer_count': customer_count}

    def get_employee_count(self, obj):
        return obj.employees.exclude(status='OFFLINE').count()


class EmployeeSerializer(serializers.ModelSerializer):
    current_zone_name = serializers.CharField(
        source='current_zone.name', read_only=True, default=None
    )

    class Meta:
        model = Employee
        fields = [
            'id', 'name', 'username', 'skill_tags', 'status',
            'break_ends_at', 'is_active',
            'current_zone', 'current_zone_name',
            'last_assigned_at', 'auth_token', 'created_at',
        ]
        read_only_fields = ['auth_token', 'created_at', 'break_ends_at']


class TaskEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskEvent
        fields = ['id', 'event_type', 'timestamp', 'details']


class TaskSerializer(serializers.ModelSerializer):
    events = TaskEventSerializer(many=True, read_only=True)
    assigned_employee_name = serializers.CharField(
        source='assigned_employee.name', read_only=True, default=None
    )
    zone_name = serializers.CharField(
        source='zone.name', read_only=True
    )

    class Meta:
        model = Task
        fields = [
            'id', 'zone', 'zone_name', 'assigned_employee',
            'assigned_employee_name', 'status', 'score_at_assignment',
            'reassignment_count', 'needs_manager_attention',
            'created_at', 'acknowledged_at', 'completed_at', 'events',
        ]
        read_only_fields = [
            'score_at_assignment', 'reassignment_count',
            'needs_manager_attention', 'created_at',
        ]


class ZoneStatusSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the manager dashboard zone status view."""
    current_threshold = serializers.SerializerMethodField()
    active_task_count = serializers.SerializerMethodField()
    checked_in_employees = serializers.SerializerMethodField()

    class Meta:
        model = Zone
        fields = [
            'id', 'name', 'current_state', 'required_skill',
            'current_threshold', 'active_task_count', 'checked_in_employees',
        ]

    def get_current_threshold(self, obj):
        density, customer_count = obj.get_current_threshold()
        return {'density': density, 'customer_count': customer_count}

    def get_active_task_count(self, obj):
        return obj.tasks.exclude(status__in=['COMPLETED', 'CLEARED']).count()

    def get_checked_in_employees(self, obj):
        return list(
            obj.employees.exclude(status='OFFLINE').values_list('name', flat=True)
        )


class TaskHistorySerializer(serializers.ModelSerializer):
    """Serializer for demo metrics: response times, etc."""
    assigned_employee_name = serializers.CharField(
        source='assigned_employee.name', read_only=True, default=None
    )
    zone_name = serializers.CharField(source='zone.name', read_only=True)
    response_time_seconds = serializers.SerializerMethodField()
    resolution_time_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'zone_name', 'assigned_employee_name', 'status',
            'created_at', 'acknowledged_at', 'completed_at',
            'response_time_seconds', 'resolution_time_seconds',
            'needs_manager_attention', 'reassignment_count',
        ]

    def get_response_time_seconds(self, obj):
        if obj.acknowledged_at and obj.created_at:
            return (obj.acknowledged_at - obj.created_at).total_seconds()
        return None

    def get_resolution_time_seconds(self, obj):
        if obj.completed_at and obj.created_at:
            return (obj.completed_at - obj.created_at).total_seconds()
        return None


class EmployeeStatsSerializer(serializers.Serializer):
    """Per-employee analytics stats (not a ModelSerializer — built from aggregated data)."""
    employee_id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.CharField()
    break_ends_at = serializers.DateTimeField(allow_null=True)
    acknowledged = serializers.IntegerField()
    missed = serializers.IntegerField()
    ack_rate = serializers.FloatField(allow_null=True)
