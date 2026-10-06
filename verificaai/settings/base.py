from __future__ import annotations

import os
from pathlib import Path

from app.core.config import Settings

BASE_DIR = Path(__file__).resolve().parents[2]
APP_SETTINGS = Settings()

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if APP_SETTINGS.app_env == "production":
        raise RuntimeError("DJANGO_SECRET_KEY is required in production")
    SECRET_KEY = "django-insecure-verificaai-local-development-only"

DEBUG = APP_SETTINGS.app_env == "local"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "analyses.apps.AnalysesConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "verificaai.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
WSGI_APPLICATION = "verificaai.wsgi.application"
ASGI_APPLICATION = "verificaai.asgi.application"

legacy_url = APP_SETTINGS.database_url
if not legacy_url.startswith("sqlite:///"):
    raise ValueError("The Django bootstrap currently requires a SQLite DATABASE_URL")
legacy_path = Path(legacy_url.removeprefix("sqlite:///"))
django_path = legacy_path.with_name(f"{legacy_path.stem}-django{legacy_path.suffix}")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / django_path,
        "OPTIONS": {"timeout": 5},
    }
}

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
