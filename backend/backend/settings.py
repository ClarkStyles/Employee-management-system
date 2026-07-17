"""
Django settings for Smart Employee Reallocation System.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(Path(__file__).resolve().parent.parent.parent / '.env')

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'rest_framework',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'static'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'
ASGI_APPLICATION = 'backend.asgi.application'

# Database — SQLite for prototype, Postgres for production
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Redis configuration
REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))

# Channel Layers — use Redis when explicitly enabled, otherwise fall back to an
# in-memory layer so the local demo works without a live Redis server.
USE_REDIS_CHANNEL_LAYER = os.getenv('USE_REDIS_CHANNEL_LAYER', 'false').lower() in ('true', '1', 'yes')

if USE_REDIS_CHANNEL_LAYER:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [
                    {
                        'address': f'redis://{REDIS_HOST}:{REDIS_PORT}/0',
                    }
                ],
                'prefix': 'srs',
                'expiry': 60,
                'symmetric_encryption_keys': [],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# DRF configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'core.middleware.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

# Assignment engine weights
WEIGHT_PROXIMITY = float(os.getenv('WEIGHT_PROXIMITY', 0.5))
WEIGHT_ZONE_LOAD = float(os.getenv('WEIGHT_ZONE_LOAD', 0.3))
WEIGHT_SKILL_MATCH = float(os.getenv('WEIGHT_SKILL_MATCH', 0.2))

# Task timeouts
ACK_TIMEOUT_SECONDS = int(os.getenv('ACK_TIMEOUT_SECONDS', 45))
MAX_REASSIGNMENTS = int(os.getenv('MAX_REASSIGNMENTS', 2))
HYSTERESIS_WINDOW_SECONDS = int(os.getenv('HYSTERESIS_WINDOW_SECONDS', 60))

# Snapshot directory
SNAPSHOT_DIR = Path(os.getenv('SNAPSHOT_DIR', BASE_DIR.parent / 'snapshots'))

# Session cookie settings (needed for manager portal WS auth)
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Allow CORS for dev (manager portal on same origin, so not needed for prod)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
