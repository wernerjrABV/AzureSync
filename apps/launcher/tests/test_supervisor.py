from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from azuresync_launcher.paths import AppPaths, InstanceNames
from azuresync_launcher.supervisor import (
    CREATE_NO_WINDOW,
    LauncherConfig,
    LauncherError,
    ServiceSupervisor,
)


class FakeResponse:
    def __init__(self, payload: dict[str, str], status: int = 200):
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args) -> None:
        return None


class FakeProcess:
    def __init__(self, name: str, handle: int):
        self.name = name
        self._handle = handle
        self.poll_result = None
        self.wait_result = None
        self.wait_timeout = None
        self.wait_calls: list[float] = []
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return self.poll_result

    def wait(self, timeout: float):
        self.wait_timeout = timeout
        self.wait_calls.append(timeout)
        if self.poll_result is None:
            if self.wait_result is not None:
                self.poll_result = self.wait_result
                return self.wait_result
            raise subprocess.TimeoutExpired(self.name, timeout)
        return self.poll_result

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1
        self.poll_result = -9


class FakeJob:
    def __init__(self):
        self.assigned_handles: list[int] = []
        self.closed = False

    def assign(self, handle: int) -> None:
        self.assigned_handles.append(handle)

    def close(self) -> None:
        self.closed = True


class FakeStopEvent:
    def __init__(self):
        self._is_set = False

    def is_set(self) -> bool:
        return self._is_set

    def set(self) -> None:
        self._is_set = True


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def paths(tmp_path: Path) -> AppPaths:
    install_dir = tmp_path / "bundle"
    sync_executable = install_dir / "_services" / "sync-service" / "sync-service.exe"
    api_executable = install_dir / "_services" / "api-read" / "api-read.exe"
    sync_executable.parent.mkdir(parents=True)
    api_executable.parent.mkdir(parents=True)
    sync_executable.write_text("sync", encoding="utf-8")
    api_executable.write_text("api", encoding="utf-8")

    return AppPaths.discover(
        executable=install_dir / "AzureSync.exe",
        local_app_data=tmp_path / "LocalAppData",
    )


@pytest.fixture
def config(paths: AppPaths) -> LauncherConfig:
    return LauncherConfig(
        paths=paths,
        names=InstanceNames.for_data_root(paths.data_dir.parent),
    )


@pytest.fixture
def supervisor_harness(config: LauncherConfig):
    processes = [
        FakeProcess("sync-service", 101),
        FakeProcess("api-read", 202),
    ]
    popen_calls: list[SimpleNamespace] = []
    health_results: list[bool] = []
    browser_calls: list[str] = []
    clock = Clock()
    job = FakeJob()
    stop_event = FakeStopEvent()

    def popen(*args, **kwargs):
        call = SimpleNamespace(args=args[0], **kwargs)
        popen_calls.append(call)
        return processes[len(popen_calls) - 1]

    def urlopen(url: str, timeout: float):
        result = health_results.pop(0)
        if result:
            return FakeResponse({"status": "ok"})
        raise OSError(f"{url} unavailable")

    def open_browser(url: str) -> None:
        browser_calls.append(url)

    supervisor = ServiceSupervisor(
        config,
        stop_event=stop_event,
        popen=popen,
        urlopen=urlopen,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        open_browser=open_browser,
        job_factory=lambda: job,
    )

    return SimpleNamespace(
        supervisor=supervisor,
        config=config,
        processes=processes,
        popen_calls=popen_calls,
        health_results=health_results,
        browser_calls=browser_calls,
        clock=clock,
        job=job,
        stop_event=stop_event,
    )


def test_start_passes_only_portable_runtime_configuration(supervisor_harness, monkeypatch):
    monkeypatch.setenv("AZURE_DEVOPS_API_KEY", "secret")

    supervisor_harness.supervisor.start()

    sync_call = supervisor_harness.popen_calls[0]
    api_call = supervisor_harness.popen_calls[1]

    assert sync_call.env["DATABASE_URL"] == ""
    assert sync_call.env["SQLITE_DATABASE_PATH"] == str(
        supervisor_harness.config.paths.database_path
    )
    assert sync_call.env["AZURESYNC_STOP_FILE"] == str(
        supervisor_harness.config.paths.stop_file
    )
    assert api_call.env["API_READ_PORT"] == "5173"
    assert api_call.env["SYNC_SERVICE_BASE_URL"] == "http://127.0.0.1:5000"
    assert "AZURE_DEVOPS_API_KEY" not in sync_call.env
    assert "AZURE_DEVOPS_API_KEY" not in api_call.env
    assert sync_call.cwd == supervisor_harness.config.paths.sync_executable.parent
    assert api_call.cwd == supervisor_harness.config.paths.api_executable.parent
    assert sync_call.creationflags == CREATE_NO_WINDOW
    assert api_call.creationflags == CREATE_NO_WINDOW
    assert supervisor_harness.job.assigned_handles == [101, 202]


def test_waits_for_both_health_checks_before_opening_browser(supervisor_harness):
    supervisor_harness.health_results.extend([False, True, False, True, True])

    supervisor_harness.supervisor.start()
    supervisor_harness.supervisor.wait_until_healthy()

    assert supervisor_harness.browser_calls == ["http://127.0.0.1:5173"]
    assert supervisor_harness.clock.sleeps == [0.25, 0.25]


def test_timeout_during_health_checks_stops_children_and_reports_logs(supervisor_harness):
    supervisor_harness.health_results.extend([False] * 400)

    supervisor_harness.supervisor.start()

    with pytest.raises(LauncherError, match="timed out waiting for health checks"):
        supervisor_harness.supervisor.wait_until_healthy()

    assert supervisor_harness.config.paths.stop_file.exists() is False
    assert supervisor_harness.processes[0].terminate_calls == 1
    assert supervisor_harness.processes[1].terminate_calls == 1
    assert supervisor_harness.job.closed is True


def test_stop_event_requests_graceful_child_shutdown(
    supervisor_harness, paths: AppPaths
):
    supervisor_harness.supervisor.start()

    supervisor_harness.processes[0].wait_result = 0
    supervisor_harness.processes[1].wait_result = 0
    supervisor_harness.stop_event.set()
    supervisor_harness.supervisor.monitor_until_stop()

    assert paths.stop_file.exists() is False
    assert all(process.wait_timeout == 30.0 for process in supervisor_harness.processes)
    assert supervisor_harness.job.closed is True


def test_child_crash_stops_peer_and_reports_log(supervisor_harness):
    supervisor_harness.supervisor.start()

    supervisor_harness.processes[0].poll_result = 17

    with pytest.raises(LauncherError, match="sync-service"):
        supervisor_harness.supervisor.monitor_until_stop()

    assert supervisor_harness.config.paths.stop_file.exists() is False
    assert supervisor_harness.processes[1].terminate_calls == 1
    assert supervisor_harness.job.closed is True


def test_start_rejects_occupied_port_before_spawning(supervisor_harness, monkeypatch):
    monkeypatch.setattr(
        "azuresync_launcher.supervisor.is_port_available",
        lambda _host, port: port != 5000,
    )

    with pytest.raises(LauncherError, match="Port 5000"):
        supervisor_harness.supervisor.start()

    assert supervisor_harness.popen_calls == []


def test_start_rejects_missing_internal_executable(supervisor_harness):
    missing_executable = supervisor_harness.config.paths.api_executable
    missing_executable.unlink()

    with pytest.raises(LauncherError, match="api-read.exe"):
        supervisor_harness.supervisor.start()

    assert supervisor_harness.popen_calls == []
