import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
# Provide SECRET_KEY via the environment in production. The fallback is only for
# local development and must never be used on a deployed host.
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-local-dev-only-change-in-production',
)

# SECURITY WARNING: never run with DEBUG = True in production.
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.staticfiles',
    'django.contrib.sessions',
    'analyzer',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',          # MUST be first
    'django.contrib.sessions.middleware.SessionMiddleware',   # required for request.session
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',              # protects the POST upload
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # near last
]

# ── Security headers (safe for local + production; no HTTPS required) ──
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

ROOT_URLCONF = 'chat_analyzer_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
            ],
        },
    },
]

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

# No database
DATABASES = {}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Session: in-memory only (no disk writes). The session carries the computed
# analysis from upload → dashboard. Keeping it in the local-memory cache means
# the chat data never touches disk, which is what makes the "your chat text is
# never stored" claim true.
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_COOKIE_AGE = 3600  # 1 hour — analysis expires

CACHES = {
    'default': {
        # locmem is per-process and does NOT persist across restarts — correct
        # for this single-process / privacy-first use case. For a multi-worker
        # production deploy, swap this for Redis so sessions are shared.
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}