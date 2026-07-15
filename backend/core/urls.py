"""
REST API URL configuration.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'zones', views.ZoneViewSet)
router.register(r'employees', views.EmployeeViewSet, basename='employee')
router.register(r'tasks', views.TaskViewSet)

urlpatterns = [
    path('', include(router.urls)),
    # Employee auth
    path('auth/token/', views.auth_token, name='auth-token'),
    path('auth/register/', views.register_employee, name='auth-register'),
    # Manager auth (session-based)
    path('auth/manager/login/', views.manager_login, name='manager-login'),
    path('auth/manager/logout/', views.manager_logout, name='manager-logout'),
    path('auth/manager/me/', views.manager_me, name='manager-me'),
    # Analytics
    path('dashboard/employee_stats', views.employee_stats, name='employee-stats'),
]
