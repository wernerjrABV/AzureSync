from pathlib import Path

from dotenv import dotenv_values


_ENV = dotenv_values(Path(__file__).resolve().parents[3] / ".env")


def get_database_url() -> str:
    return _ENV.get("DATABASE_URL", "") or ""


def get_sqlite_database_path() -> str:
    value = Path(_ENV.get("SQLITE_DATABASE_PATH", "apps/data/azure_sync.sqlite3"))
    return str(value if value.is_absolute() else (Path(__file__).resolve().parents[3] / value))


def get_host() -> str:
    return _ENV.get("API_READ_HOST", "127.0.0.1")


def get_port() -> int:
    return int(_ENV.get("API_READ_PORT", "5001"))


def get_sync_service_base_url() -> str:
    return _ENV.get("SYNC_SERVICE_BASE_URL", "http://127.0.0.1:5000")


def get_cors_allowed_origins() -> list[str]:
    value = _ENV.get(
        "API_READ_CORS_ORIGIN", "http://127.0.0.1:5173,http://localhost:5173"
    )
    return [origin.strip() for origin in value.split(",") if origin.strip()]
