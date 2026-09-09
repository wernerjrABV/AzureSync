from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .paths import AppPaths, InstanceNames
from .windows_control import KillOnCloseJob

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


class StopEvent(Protocol):
    def wait(self, timeout_ms: int) -> bool: ...


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    executable: Path
    health_url: str
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class LauncherConfig:
    paths: AppPaths
    names: InstanceNames
    startup_timeout: float = 30.0
    poll_interval: float = 0.25
    shutdown_timeout: float = 30.0


class LauncherError(RuntimeError):
    pass


class ServiceSupervisor:
    def __init__(
        self,
        config: LauncherConfig,
        *,
        stop_event: StopEvent,
        popen=subprocess.Popen,
        urlopen=urllib.request.urlopen,
        monotonic=time.monotonic,
        sleep=time.sleep,
        open_browser=webbrowser.open,
        job_factory=KillOnCloseJob.create,
    ):
        self.config = config
        self.stop_event = stop_event
        self.popen = popen
        self.urlopen = urlopen
        self.monotonic = monotonic
        self.sleep = sleep
        self.open_browser = open_browser
        self.job_factory = job_factory
        self.services = _build_services(config.paths)
        self.processes: list[object] = []
        self._process_by_service: dict[str, object] = {}
        self._job = None
        self._log_handles: list[object] = []
        self._browser_opened = False
        self._cleanup_done = False

    def _child_environment(self) -> dict[str, str]:
        return {
            "DATABASE_URL": "",
            "SQLITE_DATABASE_PATH": str(self.config.paths.database_path),
            "SYNC_SERVICE_BASE_URL": "http://127.0.0.1:5000",
            "API_READ_HOST": "127.0.0.1",
            "API_READ_PORT": "5173",
            "AZURESYNC_STOP_FILE": str(self.config.paths.stop_file),
        }

    def start(self) -> None:
        self._ensure_directories()
        self._clear_stop_file()
        self._validate_startup()
        self._job = self.job_factory()
        environment = self._child_environment()
        try:
            for service in self.services:
                stdout_handle = service.stdout_path.open("a", encoding="utf-8")
                stderr_handle = service.stderr_path.open("a", encoding="utf-8")
                self._log_handles.extend([stdout_handle, stderr_handle])
                process = self.popen(
                    [str(service.executable)],
                    cwd=service.executable.parent,
                    env=environment,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    creationflags=CREATE_NO_WINDOW,
                )
                self.processes.append(process)
                self._process_by_service[service.name] = process
                self._job.assign(process._handle)
        except Exception:
            self.stop()
            raise

    def wait_until_healthy(self) -> None:
        deadline = self.monotonic() + self.config.startup_timeout
        while True:
            unhealthy_service = None
            for service in self.services:
                self._raise_if_exited(service)
                if not self._is_service_healthy(service):
                    unhealthy_service = service
                    break
            if unhealthy_service is None:
                if not self._browser_opened:
                    self.open_browser("http://127.0.0.1:5173")
                    self._browser_opened = True
                return
            if self.monotonic() >= deadline:
                self.stop()
                raise LauncherError(
                    f"timed out waiting for health checks. See {unhealthy_service.stderr_path}"
                )
            self.sleep(self.config.poll_interval)

    def monitor_until_stop(self) -> None:
        while True:
            if self.stop_event.wait(0):
                self.stop()
                return
            for service in self.services:
                process = self._process_by_service.get(service.name)
                if process is not None and process.poll() is not None:
                    self.stop()
                    raise LauncherError(
                        f"{service.name} exited unexpectedly. See {service.stderr_path}"
                    )
            self.sleep(self.config.poll_interval)

    def stop(self) -> None:
        if self._cleanup_done:
            return
        self._cleanup_done = True

        self._write_stop_file()
        deadline = self.monotonic() + self.config.shutdown_timeout
        survivors: list[object] = []
        for process in self.processes:
            if process.poll() is not None:
                continue
            remaining = max(0.0, deadline - self.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                survivors.append(process)

        for process in survivors:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    process.kill()

        self._clear_stop_file()
        for handle in self._log_handles:
            try:
                handle.close()
            except Exception:
                pass
        self._log_handles.clear()
        if self._job is not None:
            self._job.close()
            self._job = None

    def _ensure_directories(self) -> None:
        self.config.paths.data_dir.mkdir(parents=True, exist_ok=True)
        self.config.paths.log_dir.mkdir(parents=True, exist_ok=True)
        self.config.paths.run_dir.mkdir(parents=True, exist_ok=True)

    def _validate_startup(self) -> None:
        if not is_port_available("127.0.0.1", 5000):
            raise LauncherError("Port 5000 is already in use.")
        if not is_port_available("127.0.0.1", 5173):
            raise LauncherError("Port 5173 is already in use.")
        for service in self.services:
            if not service.executable.exists():
                raise LauncherError(f"Missing internal executable: {service.executable}")

    def _is_service_healthy(self, service: ServiceSpec) -> bool:
        try:
            with self.urlopen(service.health_url, timeout=self.config.poll_interval) as response:
                if getattr(response, "status", None) != 200:
                    return False
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return False
        return payload == {"status": "ok"}

    def _raise_if_exited(self, service: ServiceSpec) -> None:
        process = self._process_by_service[service.name]
        if process.poll() is not None:
            self.stop()
            raise LauncherError(
                f"{service.name} exited before becoming healthy. See {service.stderr_path}"
            )

    def _write_stop_file(self) -> None:
        stop_file = self.config.paths.stop_file
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = stop_file.with_suffix(".tmp")
        temp_file.write_text("stop\n", encoding="utf-8")
        os.replace(temp_file, stop_file)

    def _clear_stop_file(self) -> None:
        try:
            self.config.paths.stop_file.unlink()
        except FileNotFoundError:
            return


def _build_services(paths: AppPaths) -> list[ServiceSpec]:
    return [
        ServiceSpec(
            name="sync-service",
            executable=paths.sync_executable,
            health_url="http://127.0.0.1:5000/health",
            stdout_path=paths.log_dir / "sync-service.stdout.log",
            stderr_path=paths.log_dir / "sync-service.stderr.log",
        ),
        ServiceSpec(
            name="api-read",
            executable=paths.api_executable,
            health_url="http://127.0.0.1:5173/health",
            stdout_path=paths.log_dir / "api-read.stdout.log",
            stderr_path=paths.log_dir / "api-read.stderr.log",
        ),
    ]
