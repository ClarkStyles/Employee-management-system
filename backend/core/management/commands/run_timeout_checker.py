import time
from django.core.management.base import BaseCommand
from core.state_machine import check_acknowledgment_timeouts

class Command(BaseCommand):
    help = 'Run the acknowledgment timeout checker periodically'

    def handle(self, *args, **options):
        self.stdout.write('Starting timeout checker loop (every 10s)...')
        while True:
            try:
                actions = check_acknowledgment_timeouts()
                if actions:
                    for task, action, new_emp in actions:
                        emp_str = new_emp.name if new_emp else "None"
                        self.stdout.write(f"Task {task.id} -> {action} (new emp: {emp_str})")
            except Exception as e:
                self.stderr.write(f"Error in timeout checker: {e}")
            time.sleep(10)
