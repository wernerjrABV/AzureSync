from app import config


def test_environment_values_override_dotenv_even_when_empty(monkeypatch):
    monkeypatch.setattr(
        config,
        "_ENV",
        {
            "DATABASE_URL": "postgresql://from-file",
            "SQLITE_DATABASE_PATH": "from-file.sqlite3",
            "API_READ_HOST": "from-file-host",
            "API_READ_PORT": "4999",
            "SYNC_SERVICE_BASE_URL": "http://from-file:5000",
            "AZURESYNC_WEB_DIST_PATH": r"C:\from-file\web",
        },
    )
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SQLITE_DATABASE_PATH", r"C:\portable\azure_sync.sqlite3")
    monkeypatch.setenv("API_READ_HOST", "127.0.0.1")
    monkeypatch.setenv("API_READ_PORT", "5173")
    monkeypatch.setenv("SYNC_SERVICE_BASE_URL", "http://127.0.0.1:5000")
    monkeypatch.setenv("AZURESYNC_WEB_DIST_PATH", r"C:\bundle\web")

    assert config.get_database_url() == ""
    assert config.get_sqlite_database_path() == r"C:\portable\azure_sync.sqlite3"
    assert config.get_host() == "127.0.0.1"
    assert config.get_port() == 5173
    assert config.get_sync_service_base_url() == "http://127.0.0.1:5000"
    assert config.get_web_dist_path() == r"C:\bundle\web"
