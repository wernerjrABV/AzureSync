import datetime
import threading
from unittest.mock import ANY, MagicMock, patch

import pytest

from app import db, repository as repo, routes
from app.routes import create_app


@pytest.fixture
def sqlite_db_path(tmp_path):
    return tmp_path / "sync-service-routes.db"


@pytest.fixture
def db_conn(sqlite_db_path):
    conn = db.SQLiteConnection(sqlite_db_path)
    db.init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(db_conn, sqlite_db_path):
    app = create_app(conn_factory=lambda: db.SQLiteConnection(sqlite_db_path))
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


def test_api_list_area_paths_returns_json_safe_configuration_and_status(client, db_conn):
    area_path_id = repo.create_area_path(
        db_conn,
        "org",
        "proj",
        "proj\\A",
        incluir_subpaths=True,
        ativo=False,
        intervalo_minutos=45,
    )
    synced_at = datetime.datetime(2026, 7, 20, 10, 30, 0)
    history_loaded_at = datetime.datetime(2026, 7, 20, 10, 31, 0)
    repo.update_area_path(
        db_conn,
        area_path_id,
        is_running=True,
        last_sync_at=synced_at,
        last_sync_status="ok",
        last_sync_count=3,
        last_error_msg=None,
        history_loaded_at=history_loaded_at,
    )
    db_conn.commit()

    response = client.get("/api/area-paths")

    assert response.status_code == 200
    assert response.get_json() == {
        "data": [
            {
                "id": area_path_id,
                "organization": "org",
                "project": "proj",
                "area_path": "proj\\A",
                "incluir_subpaths": True,
                "ativo": False,
                "intervalo_minutos": 45,
                "is_running": True,
                "last_sync_at": "2026-07-20T10:30:00",
                "last_sync_status": "ok",
                "last_sync_count": 3,
                "last_error_msg": None,
                "created_at": ANY,
                "history_loaded_at": "2026-07-20T10:31:00",
            }
        ]
    }


def test_api_create_area_path_returns_created_json(client, db_conn):
    payload = {
        "organization": "org",
        "project": "proj",
        "area_path": "proj\\B",
        "incluir_subpaths": False,
        "ativo": True,
        "intervalo_minutos": 30,
    }

    response = client.post("/api/area-paths", json=payload)

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body | {"id": body["id"], "created_at": body["created_at"]} == {
        "id": body["id"],
        **payload,
        "is_running": False,
        "last_sync_at": None,
        "last_sync_status": None,
        "last_sync_count": None,
        "last_error_msg": None,
        "created_at": body["created_at"],
        "history_loaded_at": None,
    }
    assert repo.get_area_path(db_conn, body["id"])["area_path"] == "proj\\B"
    assert isinstance(body["created_at"], str)


def test_api_update_area_path_returns_updated_json(client, db_conn):
    area_path_id = repo.create_area_path(db_conn, "old-org", "old-proj", "old\\A")
    db_conn.commit()
    payload = {
        "organization": "org",
        "project": "proj",
        "area_path": "proj\\B",
        "incluir_subpaths": False,
        "ativo": False,
        "intervalo_minutos": 15,
    }

    response = client.put(f"/api/area-paths/{area_path_id}", json=payload)

    assert response.status_code == 200
    assert response.get_json()["data"] | {"id": area_path_id} == {
        "id": area_path_id,
        **payload,
        "is_running": False,
        "last_sync_at": None,
        "last_sync_status": None,
        "last_sync_count": None,
        "last_error_msg": None,
        "created_at": ANY,
        "history_loaded_at": None,
    }


def test_api_delete_area_path_returns_no_content(client, db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    response = client.delete(f"/api/area-paths/{area_path_id}")

    assert response.status_code == 204
    assert repo.get_area_path(db_conn, area_path_id) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"organization": "", "project": "proj", "area_path": "proj\\A", "intervalo_minutos": 60},
        {"organization": "org", "project": "", "area_path": "proj\\A", "intervalo_minutos": 60},
        {"organization": "org", "project": "proj", "area_path": "", "intervalo_minutos": 60},
        {"organization": "org", "project": "proj", "area_path": "proj\\A", "intervalo_minutos": 0},
        {"organization": "org", "project": "proj", "area_path": "proj\\A", "intervalo_minutos": -1},
    ],
)
def test_api_create_area_path_rejects_empty_fields_and_non_positive_intervals(client, payload):
    response = client.post("/api/area-paths", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid area path payload"}


@pytest.mark.parametrize("method", ["put", "delete"])
def test_api_returns_json_404_for_unknown_area_path(client, method):
    response = getattr(client, method)(
        "/api/area-paths/999",
        json={
            "organization": "org",
            "project": "proj",
            "area_path": "proj\\A",
            "intervalo_minutos": 60,
        }
        if method == "put"
        else None,
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "area path not found"}


def test_api_sync_returns_json_404_for_unknown_area_path(client):
    response = client.post("/api/area-paths/999/sync")

    assert response.status_code == 404
    assert response.get_json() == {"error": "area path not found"}


def test_api_sync_returns_json_409_when_already_running(client, db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    repo.try_acquire_lock(db_conn, area_path_id)
    db_conn.commit()

    response = client.post(f"/api/area-paths/{area_path_id}/sync")

    assert response.status_code == 409
    assert response.get_json() == {"error": "sync already running"}


@patch("app.routes.sync_service.run_sync")
@patch("app.routes.start_manual_sync", return_value=True)
def test_api_sync_starts_background_worker_without_running_sync_in_request(
    mock_start_manual_sync, mock_run_sync, client, db_conn
):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    response = client.post(f"/api/area-paths/{area_path_id}/sync")

    assert response.status_code == 202
    assert response.get_json() == {"status": "started"}
    submitted_conn_factory, submitted_area_path_id = mock_start_manual_sync.call_args.args
    assert callable(submitted_conn_factory)
    assert submitted_conn_factory is not db_conn
    assert submitted_area_path_id == area_path_id
    mock_run_sync.assert_not_called()


@patch("app.routes.start_manual_sync", return_value=False)
def test_api_sync_returns_409_when_background_worker_is_already_queued(
    mock_start_manual_sync, client, db_conn
):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    response = client.post(f"/api/area-paths/{area_path_id}/sync")

    assert response.status_code == 409
    assert response.get_json() == {"error": "sync already running"}
    mock_start_manual_sync.assert_called_once()


def test_api_sync_returns_json_503_and_releases_reservation_when_queueing_fails(
    client, db_conn, monkeypatch
):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    class FailingExecutor:
        def submit(self, *args):
            raise RuntimeError("executor unavailable")

    monkeypatch.setattr(routes, "_MANUAL_SYNC_EXECUTOR", FailingExecutor())

    response = client.post(f"/api/area-paths/{area_path_id}/sync")

    assert response.status_code == 503
    assert response.get_json() == {"error": "sync could not be queued"}
    assert area_path_id not in routes._MANUAL_SYNC_IDS


@patch("app.routes.AdoClient")
@patch("app.routes.sync_service.run_sync")
def test_manual_sync_worker_uses_its_own_connection_and_closes_it_on_success(
    mock_run_sync, mock_ado_client, sqlite_db_path, db_conn
):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    worker_conn = db.SQLiteConnection(sqlite_db_path)
    worker_conn.close = MagicMock(wraps=worker_conn.close)

    routes._run_manual_sync_worker(lambda: worker_conn, area_path_id)

    mock_ado_client.assert_called_once_with("org", "proj")
    mock_run_sync.assert_called_once_with(worker_conn, ANY, mock_ado_client.return_value)
    assert worker_conn.connection is not db_conn.connection
    worker_conn.close.assert_called_once()


@patch("app.routes.sync_service.run_sync", side_effect=RuntimeError("sync exploded"))
def test_manual_sync_worker_closes_its_connection_when_sync_errors(
    mock_run_sync, sqlite_db_path, db_conn
):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    worker_conn = db.SQLiteConnection(sqlite_db_path)
    worker_conn.close = MagicMock(wraps=worker_conn.close)

    with pytest.raises(RuntimeError, match="sync exploded"):
        routes._run_manual_sync_worker(lambda: worker_conn, area_path_id)

    mock_run_sync.assert_called_once()
    worker_conn.close.assert_called_once()


def test_start_manual_sync_allows_only_one_concurrent_submission(monkeypatch):
    class RecordingExecutor:
        def __init__(self):
            self.submissions = []

        def submit(self, *args):
            self.submissions.append(args)

    executor = RecordingExecutor()
    monkeypatch.setattr(routes, "_MANUAL_SYNC_EXECUTOR", executor)
    barrier = threading.Barrier(3)
    results = []

    def start():
        barrier.wait()
        results.append(routes.start_manual_sync(lambda: None, 42))

    workers = [threading.Thread(target=start) for _ in range(2)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join()

    assert sorted(results) == [False, True]
    assert executor.submissions == [(routes._run_manual_sync_worker, ANY, 42)]
    routes._MANUAL_SYNC_IDS.discard(42)
