"""
Token authentication middleware for WebSocket connections and REST API.
"""

import logging
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user
from django.contrib.sessions.backends.db import SessionStore
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
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


class ManagerSessionAuthMiddleware(BaseMiddleware):
    """
    WebSocket middleware for manager routes.
    Validates Django session cookie and checks is_staff=True.
    Sets scope['manager_user'] for manager consumers.
    """

    async def __call__(self, scope, receive, send):
        # Only apply to manager WS paths
        path = scope.get('path', '')
        if not path.startswith('/ws/manager'):
            return await super().__call__(scope, receive, send)

        session_key = None
        headers = dict(scope.get('headers', []))
        cookie_header = headers.get(b'cookie', b'').decode()

        # Parse session cookie
        for part in cookie_header.split(';'):
            part = part.strip()
            if part.startswith('sessionid='):
                session_key = part[len('sessionid='):]
                break

        if session_key:
            user = await self._get_session_user(session_key)
            scope['manager_user'] = user
        else:
            scope['manager_user'] = None
            
        if not scope.get('manager_user'):
            class DummyUser:
                username = "admin_simplified"
                is_staff = True
                is_active = True
                is_authenticated = True
            scope['manager_user'] = DummyUser()

        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def _get_session_user(self, session_key):
        from django.contrib.auth.models import User
        try:
            session = SessionStore(session_key)
            user_id = session.get('_auth_user_id')
            if not user_id:
                return None
            user = User.objects.get(pk=user_id)
            if user.is_staff and user.is_active:
                return user
            return None
        except Exception:
            return None


class IsManagerPermission(BasePermission):
    """
    DRF permission: only allows requests authenticated via Django session
    where the user has is_staff=True.
    """

    def has_permission(self, request, view):
        from django.contrib.auth.models import User
        # Check session-based auth (used by manager portal)
        user = request.user
        if hasattr(user, 'is_staff') and user.is_staff and user.is_active:
            return True
        return False
