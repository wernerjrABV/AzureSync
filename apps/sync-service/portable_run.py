import importlib
import os
import threading
import time
from pathlib import Path

from app import db
from app.credential_protection import DpapiCredentialProtector
from app.routes import create_app, shutdown_manual_syncs
from app.scheduler import build_scheduler

HOST = "127.0.0.1"
PORT = 5000


def _get_stop_file() -> Path:
    stop_file = os.environ.get("AZURESYNC_STOP_FILE")
    if not stop_file:
        raise RuntimeError("AZURESYNC_STOP_FILE is required")
    return Path(stop_file)


def _wait_for_stop(stop_file: Path) -> None:
    while not stop_file.exists():
        time.sleep(0.25)


def _serve_in_thread(server) -> threading.Thread:
    thread = threading.Thread(target=server.run, name="portable-waitress")
    thread.start()
    return thread


def _create_server(app):
    waitress = importlib.import_module("waitress")
    return waitress.create_server(app=app, host=HOST, port=PORT)


def main() -> None:
    stop_file = _get_stop_file()
    init_conn = db.get_connection()
    db.init_schema(init_conn)
    init_conn.commit()
    init_conn.close()

    credential_protector = DpapiCredentialProtector()
    app = create_app(credential_protector=credential_protector)
    scheduler = build_scheduler(credential_protector=credential_protector)
    server = _create_server(app)
    server_thread = None
    scheduler_started = False
    manual_syncs_shutdown = False
    server_closed = False

    try:
        scheduler.start()
        scheduler_started = True
        server_thread = _serve_in_thread(server)
        _wait_for_stop(stop_file)
        server.close()
        server_closed = True
        scheduler.shutdown(wait=True)
        scheduler_started = False
        shutdown_manual_syncs(wait=True)
        manual_syncs_shutdown = True
        server_thread.join()
    finally:
        if not server_closed:
            server.close()
        if scheduler_started:
            scheduler.shutdown(wait=True)
        if not manual_syncs_shutdown:
            shutdown_manual_syncs(wait=True)
        if server_thread is not None and server_thread.is_alive():
            server_thread.join()


if __name__ == "__main__":
    main()
