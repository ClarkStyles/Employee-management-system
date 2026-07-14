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

        # 2. Create Employees with login credentials
        employees = [
            {'name': 'Alice',   'username': 'alice',   'password': 'demo1234', 'skills': ['tech']},
            {'name': 'Bob',     'username': 'bob',     'password': 'demo1234', 'skills': ['cashier']},
            {'name': 'Charlie', 'username': 'charlie', 'password': 'demo1234', 'skills': ['greeter']},
            {'name': 'Diana',   'username': 'diana',   'password': 'demo1234', 'skills': ['tech', 'cashier']},
            {'name': 'Eve',     'username': 'eve',     'password': 'demo1234', 'skills': []},
            {'name': 'Frank',   'username': 'frank',   'password': 'demo1234', 'skills': []},
        ]

        for emp_data in employees:
            emp = Employee(
                name=emp_data['name'],
                username=emp_data['username'],
                skill_tags=emp_data['skills'],
                status='FREE',
                auth_token=uuid.uuid4().hex,
            )
            emp.set_password(emp_data['password'])
            emp.save()

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))
        self.stdout.write('Demo login credentials (password: demo1234 for all):')
        for emp_data in employees:
            self.stdout.write(f"  username: {emp_data['username']}")
