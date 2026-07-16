import os


def get_database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return value


def get_host() -> str:
    return os.environ.get("API_READ_HOST", "127.0.0.1")


def get_port() -> int:
    return int(os.environ.get("API_READ_PORT", "5001"))


def get_cors_allowed_origin() -> str:
    return os.environ.get("API_READ_CORS_ORIGIN", "http://127.0.0.1:5173")
