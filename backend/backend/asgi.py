"""
ASGI config — routes HTTP and WebSocket traffic.

Employee WS:  ws/employee/<token>/    → TokenAuthMiddleware          → EmployeeConsumer
Manager WS :  ws/manager/             → ManagerSessionAuthMiddleware → ManagerConsumer
              ws/manager/preview/<z>/ → ManagerSessionAuthMiddleware → PreviewConsumer
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from core.middleware import TokenAuthMiddleware, ManagerSessionAuthMiddleware
from core.routing import websocket_urlpatterns

django_asgi_app = get_asgi_application()


class CombinedAuthMiddleware:
    """
    Routes WS connections to the appropriate auth middleware:
    - /ws/manager/... → ManagerSessionAuthMiddleware
    - /ws/employee/... → TokenAuthMiddleware
    """

    def __init__(self, app):
        self.app = app
        self.employee_mw = TokenAuthMiddleware(app)
        self.manager_mw = ManagerSessionAuthMiddleware(app)

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        if path.startswith('/ws/manager'):
            return await self.manager_mw(scope, receive, send)
        return await self.employee_mw(scope, receive, send)


application = ProtocolTypeRouter({
    'http': ASGIStaticFilesHandler(django_asgi_app),
    'websocket': CombinedAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})
