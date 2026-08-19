import importlib
import os
import sys
import threading
import time
from pathlib import Path

from app.routes import create_app

HOST = "127.0.0.1"
PORT = 5173


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


def _get_bundled_web_root() -> Path:
    return Path(sys._MEIPASS) / "web"  # type: ignore[attr-defined]


def main() -> None:
    stop_file = _get_stop_file()
    app = create_app(web_dist_path=_get_bundled_web_root())
    server = _create_server(app)
    server_thread = None
    server_closed = False

    try:
        server_thread = _serve_in_thread(server)
        _wait_for_stop(stop_file)
        server.close()
        server_closed = True
        server_thread.join()
    finally:
        if not server_closed:
            server.close()
        if server_thread is not None and server_thread.is_alive():
            server_thread.join()


if __name__ == "__main__":
    main()
