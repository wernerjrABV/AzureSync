from app import config


def test_environment_values_override_dotenv_even_when_empty(monkeypatch):
    monkeypatch.setattr(
        config,
        "_ENV",
        {
            "DATABASE_URL": "postgresql://from-file",
            "SQLITE_DATABASE_PATH": "from-file.sqlite3",
        },
    )
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SQLITE_DATABASE_PATH", r"C:\portable\azure_sync.sqlite3")

    assert config.get_database_url() == ""
    assert config.get_sqlite_database_path() == r"C:\portable\azure_sync.sqlite3"
