import importlib
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _import_portable_run():
    return importlib.import_module("portable_run")


class _FakeServer:
    def __init__(self):
        self.closed = threading.Event()
        self.run_called = threading.Event()
        self.close = MagicMock(side_effect=self.closed.set)

    def run(self):
        self.run_called.set()
        self.closed.wait(timeout=5)


def test_main_requires_stop_file_env_var(monkeypatch):
    portable_run = _import_portable_run()

    monkeypatch.delenv("AZURESYNC_STOP_FILE", raising=False)

    with pytest.raises(RuntimeError, match="AZURESYNC_STOP_FILE is required"):
        portable_run.main()


def test_main_serves_until_stop_file_then_shuts_down_runtime(monkeypatch, tmp_path):
    portable_run = _import_portable_run()
    stop_file = tmp_path / "portable.stop"
    fake_server = _FakeServer()
    fake_scheduler = MagicMock()
    fake_init_conn = MagicMock()
    fake_app = object()
    fake_protector = object()
    captured = {}

    def fake_create_server(*, app, host, port):
        captured["server_args"] = {"app": app, "host": host, "port": port}
        return fake_server

    monkeypatch.setenv("AZURESYNC_STOP_FILE", str(stop_file))
    monkeypatch.setitem(sys.modules, "waitress", SimpleNamespace(create_server=fake_create_server))
    monkeypatch.setattr(portable_run.db, "get_connection", MagicMock(return_value=fake_init_conn))
    monkeypatch.setattr(portable_run.db, "init_schema", MagicMock())
    monkeypatch.setattr(portable_run, "create_app", MagicMock(return_value=fake_app))
    monkeypatch.setattr(portable_run, "build_scheduler", MagicMock(return_value=fake_scheduler))
    monkeypatch.setattr(portable_run, "shutdown_manual_syncs", MagicMock())
    monkeypatch.setattr(portable_run, "DpapiCredentialProtector", MagicMock(return_value=fake_protector))

    errors = []

    def run_main():
        try:
            portable_run.main()
        except Exception as exc:  # pragma: no cover - surfaced via assertion below
            errors.append(exc)

    worker = threading.Thread(target=run_main, name="portable-run-test")
    worker.start()

    assert fake_server.run_called.wait(timeout=5)
    stop_file.touch()
    worker.join(timeout=5)

    assert errors == []
    assert not worker.is_alive()
    portable_run.db.get_connection.assert_called_once_with()
    portable_run.db.init_schema.assert_called_once_with(fake_init_conn)
    fake_init_conn.commit.assert_called_once_with()
    fake_init_conn.close.assert_called_once_with()
    portable_run.create_app.assert_called_once_with(credential_protector=fake_protector)
    portable_run.build_scheduler.assert_called_once_with(credential_protector=fake_protector)
    fake_scheduler.start.assert_called_once_with()
    fake_scheduler.shutdown.assert_called_once_with(wait=True)
    portable_run.shutdown_manual_syncs.assert_called_once_with(wait=True)
    fake_server.close.assert_called_once_with()
    assert captured["server_args"] == {"app": fake_app, "host": "127.0.0.1", "port": 5000}
