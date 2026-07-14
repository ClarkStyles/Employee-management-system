"""
WebSocket URL routing.
"""

from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/employee/<str:token>/', consumers.EmployeeConsumer.as_asgi()),
]
