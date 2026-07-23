"""
Data models for the Smart Employee Reallocation System.
Zone, Employee, Task, TaskEvent.
"""

from django.db import models
from django.contrib.auth.hashers import check_password as django_check_password, is_password_usable
from django.utils import timezone


class Zone(models.Model):
    """Retail zone monitored by cameras."""
    name = models.CharField(max_length=100)

    # Adaptive threshold: JSON with weekday/weekend × time-of-day buckets
    # Format: {
    #   "default_threshold": 0.7,
    #   "default_customer_count": 8,
    #   "buckets": [
    #     {"days": ["mon","tue","wed","thu","fri"], "start": "09:00", "end": "12:00",
    #      "threshold": 0.8, "customer_count": 10},
    #     {"days": ["sat","sun"], "start": "10:00", "end": "18:00",
    #      "threshold": 0.9, "customer_count": 12}
    #   ]
    # }
    threshold_config = models.JSONField(default=dict)

    hysteresis_window = models.IntegerField(
        default=2,
        help_text="Seconds density must stay above/below threshold before state change"
    )

    ZONE_STATES = [('NORMAL', 'Normal'), ('ALERT', 'Alert')]
    current_state = models.CharField(max_length=10, choices=ZONE_STATES, default='NORMAL')

    required_skill = models.CharField(max_length=100, blank=True, default='')

    # Optional input source for pre-recorded or live feeds assigned to this zone.
    video_source = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Path or URL for the video/feed assigned to this zone"
    )

    # Zone adjacency stored as JSON: {"2": 1, "3": 2} = zone_id -> distance
    adjacency_map = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    def get_current_threshold(self):
        """Look up the correct threshold bucket for current day + time.
        Returns (density_threshold, customer_count_threshold) tuple.
        Falls back to default values if no bucket matches."""
        config = self.threshold_config
        if not config:
            return (0.5, 2)

        now = timezone.localtime()
        day_name = now.strftime("%a").lower()[:3]  # mon, tue, ...
        current_time = now.strftime("%H:%M")

        for bucket in config.get("buckets", []):
            if day_name in bucket.get("days", []):
                if bucket.get("start", "00:00") <= current_time < bucket.get("end", "24:00"):
                    return (bucket["threshold"], bucket["customer_count"])

        return (
            config.get("default_threshold", 0.5),
            config.get("default_customer_count", 2),
        )

    def __str__(self):
        return f"{self.name} ({self.current_state})"

    class Meta:
        ordering = ['id']


class Employee(models.Model):
    """Retail floor employee."""
    name = models.CharField(max_length=100)

    # Login credentials — username is used for login, password_hash stores Django's hashed password
    username = models.CharField(max_length=64, unique=True, default='')
    password_hash = models.CharField(max_length=256, default='')

    skill_tags = models.JSONField(default=list)  # ["checkout", "electronics", ...]

    STATUS_CHOICES = [
        ('FREE', 'Free'),
        ('ASSIGNED', 'Assigned'),
        ('ACKNOWLEDGED', 'Acknowledged'),
        ('IN_PROGRESS', 'In Progress'),
        ('ON_BREAK', 'On Break'),
        ('BUSY', 'Busy'),
        ('OFFLINE', 'Offline'),
    ]
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='OFFLINE')

    # Break management
    break_ends_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the current break expires (status=ON_BREAK)"
    )

    # Soft delete — inactive employees excluded from assignment pool
    is_active = models.BooleanField(default=True)

    current_zone = models.ForeignKey(
        Zone, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='employees'
    )
    last_assigned_at = models.DateTimeField(null=True, blank=True)

    # Session token — generated on login/register, used for WS auth
    auth_token = models.CharField(max_length=64, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        self.password_hash = raw_password

    def check_password(self, raw_password):
        if not self.password_hash:
            return False
        if self.password_hash == raw_password:
            return True
        if is_password_usable(self.password_hash):
            return django_check_password(raw_password, self.password_hash)
        return False

    def __str__(self):
        return f"{self.name} ({self.status})"

    class Meta:
        ordering = ['id']


class Task(models.Model):
    """Assignment of an employee to handle an alert zone."""
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='tasks')
    assigned_employee = models.ForeignKey(
        Employee, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='tasks'
    )

    STATUS_CHOICES = [
        ('CREATED', 'Created'),
        ('ASSIGNED', 'Assigned'),
        ('ACKNOWLEDGED', 'Acknowledged'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CLEARED', 'Cleared'),
    ]
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='CREATED')

    score_at_assignment = models.FloatField(default=0)
    reassignment_count = models.IntegerField(default=0)

    # Manager flag — set after 2 failed reassignments.
    # Task.status stays in its last real state; this is a separate boolean.
    needs_manager_attention = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        emp = self.assigned_employee.name if self.assigned_employee else 'Unassigned'
        return f"Task #{self.id} → {self.zone.name} ({self.status}, {emp})"

    class Meta:
        ordering = ['-created_at']


class TaskEvent(models.Model):
    """Audit trail entry for a task lifecycle event."""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=50)
    # Event types: CREATED, ASSIGNED, ACKNOWLEDGED, IN_PROGRESS,
    #              COMPLETED, CLEARED, ESCALATED, MANAGER_FLAGGED, REASSIGNED
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)

    def __str__(self):
        return f"{self.event_type} @ {self.timestamp}"

    class Meta:
        ordering = ['timestamp']
