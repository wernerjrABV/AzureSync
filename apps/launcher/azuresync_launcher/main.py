from __future__ import annotations

import json
import sys
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

from .paths import AppPaths, InstanceNames
from .supervisor import LauncherConfig, LauncherError, ServiceSupervisor
from .windows_control import NamedEvent, NamedMutex, show_error as default_show_error


def _is_healthy(urlopen, url: str, timeout: float) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            if getattr(response, "status", None) != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return False
    return payload == {"status": "ok"}


def _close_quietly(resource) -> None:
    if resource is None:
        return
    close = getattr(resource, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        pass


def _write_launcher_error(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        traceback.print_exc(file=handle)


def launch(
    *,
    urlopen=None,
    open_browser=None,
    sleep=None,
    monotonic=None,
    show_error=None,
    supervisor_cls=None,
) -> int:
    urlopen = urlopen or urllib.request.urlopen
    open_browser = open_browser or webbrowser.open
    sleep = sleep or time.sleep
    monotonic = monotonic or time.monotonic
    show_error = show_error or default_show_error
    supervisor_cls = supervisor_cls or ServiceSupervisor

    paths = AppPaths.discover()
    names = InstanceNames.for_data_root(paths.data_dir.parent)
    mutex = None
    stop_event = None
    try:
        mutex, acquired = NamedMutex.acquire(names.mutex)
        if not acquired:
            deadline = monotonic() + 30.0
            while True:
                if _is_healthy(urlopen, "http://127.0.0.1:5173/health", 0.25):
                    open_browser("http://127.0.0.1:5173")
                    return 0
                if monotonic() >= deadline:
                    show_error(
                        "AzureSync",
                        "AzureSync is already running but did not become healthy at http://127.0.0.1:5173.",
                    )
                    return 1
                sleep(0.25)

        stop_event = NamedEvent.create(names.stop_event)
        supervisor = supervisor_cls(
            LauncherConfig(paths=paths, names=names),
            stop_event=stop_event,
            urlopen=urlopen,
            open_browser=open_browser,
            sleep=sleep,
            monotonic=monotonic,
        )
        supervisor.start()
        supervisor.wait_until_healthy()
        supervisor.monitor_until_stop()
        return 0
    except (LauncherError, OSError):
        log_path = paths.log_dir / "launcher-error.log"
        _write_launcher_error(log_path)
        show_error("AzureSync", f"AzureSync could not start. See {log_path}.")
        return 1
    finally:
        _close_quietly(stop_event)
        _close_quietly(mutex)


def request_stop(*, show_error=None) -> int:
    show_error = show_error or default_show_error

    paths = AppPaths.discover()
    names = InstanceNames.for_data_root(paths.data_dir.parent)
    stop_event = None
    try:
        stop_event = NamedEvent.open(names.stop_event)
        stop_event.set()
        return 0
    except OSError:
        show_error("AzureSync", "AzureSync is not running.")
        return 1
    finally:
        _close_quietly(stop_event)


def entrypoint() -> int:
    executable_name = (
        Path(sys.executable).stem.lower() if getattr(sys, "frozen", False) else "azuresync"
    )
    return request_stop() if executable_name == "stopazuresync" else launch()
