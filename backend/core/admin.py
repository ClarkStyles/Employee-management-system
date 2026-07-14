from django.contrib import admin
from .models import Zone, Employee, Task, TaskEvent

@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'current_state', 'required_skill')

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'status', 'current_zone')
    list_filter = ('status',)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'zone', 'assigned_employee', 'status', 'needs_manager_attention', 'created_at')
    list_filter = ('status', 'needs_manager_attention')

@admin.register(TaskEvent)
class TaskEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'task', 'event_type', 'timestamp')
    list_filter = ('event_type',)
