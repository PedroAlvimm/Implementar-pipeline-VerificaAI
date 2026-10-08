from __future__ import annotations

from django.apps import AppConfig
from django.db.backends.signals import connection_created


def configure_sqlite_connection(sender: type, connection: object, **kwargs: object) -> None:
    if connection.vendor != "sqlite":  # type: ignore[attr-defined]
        return

    database_name = str(connection.settings_dict["NAME"])  # type: ignore[attr-defined]
    cursor = connection.connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        if database_name != ":memory:" and "mode=memory" not in database_name:
            cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


class AnalysesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analyses"

    def ready(self) -> None:
        # Runtime recovery/workers are explicitly requested by web entrypoints,
        # never during app loading, migrations, or unrelated management commands.
        connection_created.connect(
            configure_sqlite_connection,
            dispatch_uid="analyses.configure_sqlite_connection",
        )
