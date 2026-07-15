from unittest.mock import MagicMock, patch

import pytest

from app import repository as repo
from app.routes import create_app


@pytest.fixture
def client(db_conn):
    app = create_app(conn_factory=lambda: db_conn)
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_index_lists_area_paths(client, db_conn):
    repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    response = client.get("/")

    assert response.status_code == 200
    assert b"proj\\A" in response.data


def test_index_shows_auth_error_banner(client, db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    repo.update_area_path(db_conn, area_path_id, last_sync_status="auth_error")
    db_conn.commit()

    response = client.get("/")

    assert b"AZURE_DEVOPS_API_KEY" in response.data


def test_create_area_path(client, db_conn):
    response = client.post(
        "/area-paths",
        data={
            "organization": "org",
            "project": "proj",
            "area_path": "proj\\B",
            "incluir_subpaths": "on",
            "ativo": "on",
            "intervalo_minutos": "45",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    rows = repo.list_area_paths(db_conn)
    assert len(rows) == 1
    assert rows[0]["area_path"] == "proj\\B"
    assert rows[0]["intervalo_minutos"] == 45


def test_delete_area_path(client, db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    client.post(f"/area-paths/{area_path_id}/delete", follow_redirects=True)

    assert repo.get_area_path(db_conn, area_path_id) is None


@patch("app.routes.AdoClient")
@patch("app.routes.sync_service.run_sync")
def test_manual_sync_triggers_run_sync(mock_run_sync, mock_ado_client, client, db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    mock_run_sync.return_value = {"status": "ok", "items_processed": 3}

    response = client.post(f"/area-paths/{area_path_id}/sync", follow_redirects=True)

    assert response.status_code == 200
    mock_run_sync.assert_called_once()


def test_manual_sync_returns_409_when_already_running(client, db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    repo.try_acquire_lock(db_conn, area_path_id)
    db_conn.commit()

    response = client.post(f"/area-paths/{area_path_id}/sync")

    assert response.status_code == 409
