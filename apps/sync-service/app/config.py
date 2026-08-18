import os
from pathlib import Path

from dotenv import dotenv_values


_ENV = dotenv_values(Path(__file__).resolve().parents[3] / ".env")


def _get_value(name: str, default: str = "") -> str:
    if name in os.environ:
        return os.environ[name]
    return _ENV.get(name, default) or default


def get_database_url() -> str:
    return _get_value("DATABASE_URL")


def get_sqlite_database_path() -> str:
    value = Path(_get_value("SQLITE_DATABASE_PATH", "apps/data/azure_sync.sqlite3"))
    return str(
        value if value.is_absolute() else (Path(__file__).resolve().parents[3] / value)
    )
