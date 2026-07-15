import os


def get_database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return value


def get_ado_api_key() -> str:
    value = os.environ.get("AZURE_DEVOPS_API_KEY")
    if not value:
        raise RuntimeError("AZURE_DEVOPS_API_KEY environment variable is not set")
    return value
