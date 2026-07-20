from pathlib import Path

from dotenv import dotenv_values


_ENV = dotenv_values(Path(__file__).resolve().parents[3] / ".env")


def get_database_url() -> str:
    return _ENV.get("DATABASE_URL", "") or ""


def get_ado_api_key() -> str:
    value = _ENV.get("AZURE_DEVOPS_API_KEY")
    if not value:
        env_path = Path(__file__).resolve().parents[3] / ".env"
        raise RuntimeError(
            f"AZURE_DEVOPS_API_KEY não está definida no arquivo {env_path}."
        )
    return value


def get_sqlite_database_path() -> str:
    value = Path(_ENV.get("SQLITE_DATABASE_PATH", "apps/data/azure_sync.sqlite3"))
    return str(value if value.is_absolute() else (Path(__file__).resolve().parents[3] / value))
