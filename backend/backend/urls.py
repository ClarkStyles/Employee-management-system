"""
URL configuration for the backend project.
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.csrf import ensure_csrf_cookie

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
    # Manager portal (separate SPA, session-based auth)
    path('manager/', ensure_csrf_cookie(TemplateView.as_view(template_name='manager.html')),
         name='manager-portal'),
    # Employee PWA (catch-all last)
    path('', TemplateView.as_view(template_name='index.html')),
]
