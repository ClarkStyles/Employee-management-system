from django.test import TestCase

from .models import Employee, Zone


class EmployeeAuthTests(TestCase):
    def test_plaintext_passwords_are_used_for_simple_auth(self):
        employee = Employee(username='plainuser', name='Plain User', auth_token='abc123', is_active=True)
        employee.set_password('secret123')

        self.assertEqual(employee.password_hash, 'secret123')
        self.assertTrue(employee.check_password('secret123'))
        self.assertFalse(employee.check_password('wrongpass'))


class ZoneVideoSourceTests(TestCase):
    def test_zone_can_store_a_video_source(self):
        zone = Zone.objects.create(name='Zone A', video_source='videos/zone_a.mp4')

        self.assertEqual(zone.video_source, 'videos/zone_a.mp4')
