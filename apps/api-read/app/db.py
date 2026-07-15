import psycopg

from app.config import get_database_url


def get_connection() -> psycopg.Connection:
    return psycopg.connect(get_database_url())
