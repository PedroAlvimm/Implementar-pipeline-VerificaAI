from __future__ import annotations

import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path


def test_django_boots_with_localhost_defaults() -> None:
    """A missing app registration or unsafe host default must break startup."""
    local = import_module("verificaai.settings.local")

    assert "analyses.apps.AnalysesConfig" in local.INSTALLED_APPS
    assert "django.contrib.admin" in local.INSTALLED_APPS
    assert "rest_framework" in local.INSTALLED_APPS
    assert "127.0.0.1" in local.ALLOWED_HOSTS
    assert "localhost" in local.ALLOWED_HOSTS
    assert "*" not in local.ALLOWED_HOSTS
    assert local.TIME_ZONE == "UTC"
    assert local.USE_TZ is True
    assert Path(local.DATABASES["default"]["NAME"]).name == "verificaai-django.sqlite3"


def test_local_settings_prepare_database_directory(tmp_path: Path) -> None:
    """A fresh local database path must be writable without manual setup."""
    database_directory = tmp_path / "new" / "nested"
    environment = os.environ.copy()
    environment["APP_ENV"] = "local"
    environment["PROVIDER_MODE"] = "disabled"
    environment["DATABASE_URL"] = f"sqlite:///{database_directory / 'legacy.sqlite3'}"
    result = subprocess.run(
        [sys.executable, "-c", "import verificaai.settings.local"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert database_directory.is_dir()


def test_test_database_enables_foreign_keys_and_wal(tmp_path: Path) -> None:
    """Every file-backed SQLite connection must receive the safety pragmas."""
    import django
    from django.db.backends.sqlite3.base import DatabaseWrapper

    django.setup()
    test_settings = import_module("verificaai.settings.test")
    database_settings = test_settings.DATABASES["default"].copy()
    database_settings["NAME"] = str(tmp_path / "bootstrap.sqlite3")
    connection = DatabaseWrapper(database_settings, alias="bootstrap_probe")

    try:
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys")
            assert cursor.fetchone()[0] == 1
            cursor.execute("PRAGMA journal_mode")
            assert cursor.fetchone()[0].lower() == "wal"
            cursor.execute("PRAGMA busy_timeout")
            assert cursor.fetchone()[0] >= 5000
    finally:
        connection.close()


def test_secret_key_has_no_production_default() -> None:
    """Production startup must reject an absent Django signing key."""
    environment = os.environ.copy()
    environment["APP_ENV"] = "production"
    environment["PROVIDER_MODE"] = "disabled"
    environment.pop("DJANGO_SECRET_KEY", None)
    result = subprocess.run(
        [sys.executable, "-c", "import verificaai.settings.base"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr
