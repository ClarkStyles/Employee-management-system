from django.contrib import admin
from .models import Zone, Employee, Task, TaskEvent

@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'current_state', 'required_skill', 'video_source')
    search_fields = ('name', 'video_source')

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'status', 'current_zone')
    list_filter = ('status',)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "status":
            kwargs['choices'] = [
                (k, v) for k, v in Employee.STATUS_CHOICES
                if k not in ('ACKNOWLEDGED', 'IN_PROGRESS')
            ]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'zone', 'assigned_employee', 'status', 'needs_manager_attention', 'created_at')
    list_filter = ('status', 'needs_manager_attention')

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "status":
            kwargs['choices'] = [
                (k, v) for k, v in Task.STATUS_CHOICES
                if k not in ('ACKNOWLEDGED', 'IN_PROGRESS')
            ]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

@admin.register(TaskEvent)
class TaskEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'task', 'event_type', 'timestamp')
    list_filter = ('event_type',)
