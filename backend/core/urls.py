"""
REST API URL configuration.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'zones', views.ZoneViewSet)
router.register(r'employees', views.EmployeeViewSet)
router.register(r'tasks', views.TaskViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('auth/token/', views.auth_token, name='auth-token'),
    path('auth/register/', views.register_employee, name='auth-register'),
]
