import uuid
from django.core.management.base import BaseCommand
from core.models import Zone, Employee

class Command(BaseCommand):
    help = 'Seed the database with sample data for the demo.'

    def handle(self, *args, **options):
        self.stdout.write('Seeding database...')

        # Clear existing
        Zone.objects.all().delete()
        Employee.objects.all().delete()

        # 1. Create Zones
        threshold_config = {
            "default_threshold": 0.7,
            "default_customer_count": 5,
            "buckets": []
        }

        z_entrance = Zone.objects.create(
            name='Entrance',
            threshold_config=threshold_config,
            hysteresis_window=30,
            required_skill='greeter',
            adjacency_map={"2": 1, "3": 2}  # Assume ID mapping will be updated
        )
        z_electronics = Zone.objects.create(
            name='Electronics',
            threshold_config=threshold_config,
            hysteresis_window=30,
            required_skill='tech',
            adjacency_map={"1": 1, "3": 1, "4": 2}
        )
        z_checkout = Zone.objects.create(
            name='Checkout',
            threshold_config=threshold_config,
            hysteresis_window=30,
            required_skill='cashier',
            adjacency_map={"1": 2, "2": 1, "4": 1}
        )
        z_grocery = Zone.objects.create(
            name='Grocery',
            threshold_config=threshold_config,
            hysteresis_window=30,
            required_skill='',
            adjacency_map={"2": 2, "3": 1}
        )

        # Update adjacency maps with actual IDs
        z_entrance.adjacency_map = {str(z_electronics.id): 1, str(z_checkout.id): 2}
        z_entrance.save()
        z_electronics.adjacency_map = {str(z_entrance.id): 1, str(z_checkout.id): 1, str(z_grocery.id): 2}
        z_electronics.save()
        z_checkout.adjacency_map = {str(z_entrance.id): 2, str(z_electronics.id): 1, str(z_grocery.id): 1}
        z_checkout.save()
        z_grocery.adjacency_map = {str(z_electronics.id): 2, str(z_checkout.id): 1}
        z_grocery.save()

        # 2. Create Employees
        employees = [
            {'name': 'Alice (Tech)', 'skills': ['tech']},
            {'name': 'Bob (Cashier)', 'skills': ['cashier']},
            {'name': 'Charlie (Greeter)', 'skills': ['greeter']},
            {'name': 'Diana (Tech, Cashier)', 'skills': ['tech', 'cashier']},
            {'name': 'Eve (General)', 'skills': []},
            {'name': 'Frank (General)', 'skills': []},
        ]

        for i, emp_data in enumerate(employees):
            Employee.objects.create(
                name=emp_data['name'],
                skill_tags=emp_data['skills'],
                status='FREE',
                # Using simple predictable tokens for demo (emp1, emp2, ...)
                auth_token=f'emp{i+1}'
            )

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))
        self.stdout.write('Employee tokens: emp1, emp2, emp3, emp4, emp5, emp6')
