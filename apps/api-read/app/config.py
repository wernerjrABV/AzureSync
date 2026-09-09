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
    return str(value if value.is_absolute() else (Path(__file__).resolve().parents[3] / value))


def get_host() -> str:
    return _get_value("API_READ_HOST", "127.0.0.1")


def get_port() -> int:
    return int(_get_value("API_READ_PORT", "5001"))


def get_sync_service_base_url() -> str:
    return _get_value("SYNC_SERVICE_BASE_URL", "http://127.0.0.1:5000")


def get_web_dist_path() -> str | None:
    value = _get_value("AZURESYNC_WEB_DIST_PATH")
    return value or None


def get_cors_allowed_origins() -> list[str]:
    value = _get_value(
        "API_READ_CORS_ORIGIN",
        "http://127.0.0.1:5173,http://localhost:5173",
    )
    return [origin.strip() for origin in value.split(",") if origin.strip()]
