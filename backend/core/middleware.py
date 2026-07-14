"""
Token authentication middleware for WebSocket connections and REST API.
"""

import logging
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)


class TokenAuthMiddleware(BaseMiddleware):
    """
    WebSocket token auth middleware.
    Extracts employee from URL path: ws/employee/{token}/
    Sets scope['employee'] for consumers.
    """

    async def __call__(self, scope, receive, send):
        from core.models import Employee

        # Extract token from URL path
        path = scope.get('path', '')
        token = None

        # Parse: /ws/employee/{token}/
        parts = path.strip('/').split('/')
        if len(parts) >= 3 and parts[0] == 'ws' and parts[1] == 'employee':
            token = parts[2]

        # Also check query string as fallback
        if not token:
            query_string = scope.get('query_string', b'').decode()
            params = parse_qs(query_string)
            token = params.get('token', [None])[0]

        if token:
            try:
                employee = await database_sync_to_async(
                    Employee.objects.get
                )(auth_token=token)
                scope['employee'] = employee
                scope['employee_token'] = token
                logger.info(f"WebSocket auth: {employee.name} (token={token[:8]}...)")
            except Employee.DoesNotExist:
                logger.warning(f"WebSocket auth failed: invalid token {token[:8]}...")
                scope['employee'] = None
        else:
            scope['employee'] = None

        return await super().__call__(scope, receive, send)


class TokenAuthentication(BaseAuthentication):
    """
    Simple token auth for REST API.
    Header: Authorization: Token <token>
    """

    def authenticate(self, request):
        from core.models import Employee

        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Token '):
            return None

        token = auth_header[6:].strip()
        try:
            employee = Employee.objects.get(auth_token=token)
            # Return (user, auth) tuple — we use employee as the "user"
            return (employee, token)
        except Employee.DoesNotExist:
            raise AuthenticationFailed('Invalid token')
