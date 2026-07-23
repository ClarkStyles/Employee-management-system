# WebSocket URL routing.


from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/employee/<str:token>/', consumers.EmployeeConsumer.as_asgi()),
    path('ws/manager/', consumers.ManagerConsumer.as_asgi()),
    path('ws/manager/preview/<int:zone_id>/', consumers.PreviewConsumer.as_asgi()),
]
