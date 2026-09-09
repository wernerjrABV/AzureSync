from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from azuresync_launcher import main
from azuresync_launcher.paths import AppPaths, InstanceNames


class FakeHealthResponse:
    status = 200

    def read(self) -> bytes:
        return b'{"status":"ok"}'

    def __enter__(self) -> "FakeHealthResponse":
        return self

    def __exit__(self, *_args) -> None:
        return None


class FakeMutex:
    def close(self) -> None:
        return None


class FakeNamedEvent:
    def __init__(self):
        self.set_calls = 0
        self._is_set = False

    def set(self) -> None:
        self.set_calls += 1
        self._is_set = True

    def is_set(self) -> bool:
        return self._is_set

    def close(self) -> None:
        return None


class FakeSupervisor:
    def __init__(self, config, **kwargs):
        self.config = config
        self.kwargs = kwargs
        self.start_calls = 0
        self.wait_calls = 0
        self.monitor_calls = 0

    def start(self) -> None:
        self.start_calls += 1

    def wait_until_healthy(self) -> None:
        self.wait_calls += 1

    def monitor_until_stop(self) -> None:
        self.monitor_calls += 1


@pytest.fixture
def paths(tmp_path: Path) -> AppPaths:
    install_dir = tmp_path / "bundle"
    return AppPaths.discover(
        executable=install_dir / "AzureSync.exe",
        local_app_data=tmp_path / "LocalAppData",
    )


@pytest.fixture
def names(paths: AppPaths) -> InstanceNames:
    return InstanceNames.for_data_root(paths.data_dir.parent)


def test_launch_first_instance_starts_supervisor_and_monitors(paths, names, monkeypatch):
    stop_event = FakeNamedEvent()
    holder: dict[str, FakeSupervisor] = {}

    monkeypatch.setattr(main.AppPaths, "discover", classmethod(lambda cls: paths))
    monkeypatch.setattr(main.InstanceNames, "for_data_root", classmethod(lambda cls, _root: names))
    monkeypatch.setattr(main.NamedMutex, "acquire", classmethod(lambda cls, _name: (FakeMutex(), True)))
    monkeypatch.setattr(main.NamedEvent, "create", classmethod(lambda cls, _name: stop_event))

    def fake_supervisor_factory(config, **kwargs):
        holder["instance"] = FakeSupervisor(config, **kwargs)
        return holder["instance"]

    monkeypatch.setattr(main, "ServiceSupervisor", fake_supervisor_factory)

    exit_code = main.launch()

    assert exit_code == 0
    assert holder["instance"].start_calls == 1
    assert holder["instance"].wait_calls == 1
    assert holder["instance"].monitor_calls == 1
    assert holder["instance"].config.names == names


def test_launch_second_instance_reopens_browser_without_spawning(paths, names, monkeypatch):
    browser_calls: list[str] = []
    health_checks = [False, True]

    monkeypatch.setattr(main.AppPaths, "discover", classmethod(lambda cls: paths))
    monkeypatch.setattr(main.InstanceNames, "for_data_root", classmethod(lambda cls, _root: names))
    monkeypatch.setattr(main.NamedMutex, "acquire", classmethod(lambda cls, _name: (FakeMutex(), False)))
    monkeypatch.setattr(main, "ServiceSupervisor", lambda *args, **kwargs: pytest.fail("should not construct supervisor"))

    def urlopen(url: str, timeout: float):
        result = health_checks.pop(0)
        if result:
            return FakeHealthResponse()
        raise OSError(url)

    exit_code = main.launch(
        urlopen=urlopen,
        open_browser=browser_calls.append,
        sleep=lambda _seconds: None,
    )

    assert exit_code == 0
    assert browser_calls == ["http://127.0.0.1:5173"]


def test_launch_unhealthy_existing_instance_shows_native_error(paths, names, monkeypatch):
    errors: list[tuple[str, str]] = []
    current_time = {"value": 0.0}

    monkeypatch.setattr(main.AppPaths, "discover", classmethod(lambda cls: paths))
    monkeypatch.setattr(main.InstanceNames, "for_data_root", classmethod(lambda cls, _root: names))
    monkeypatch.setattr(main.NamedMutex, "acquire", classmethod(lambda cls, _name: (FakeMutex(), False)))

    exit_code = main.launch(
        urlopen=lambda _url, _timeout: (_ for _ in ()).throw(OSError("down")),
        sleep=lambda seconds: current_time.__setitem__("value", current_time["value"] + seconds),
        monotonic=lambda: current_time["value"],
        show_error=lambda title, message: errors.append((title, message)),
    )

    assert exit_code == 1
    assert errors == [("AzureSync", "AzureSync is already running but did not become healthy at http://127.0.0.1:5173.")]


def test_request_stop_signals_existing_instance(paths, names, monkeypatch):
    stop_event = FakeNamedEvent()

    monkeypatch.setattr(main.AppPaths, "discover", classmethod(lambda cls: paths))
    monkeypatch.setattr(main.InstanceNames, "for_data_root", classmethod(lambda cls, _root: names))
    monkeypatch.setattr(main.NamedEvent, "open", classmethod(lambda cls, _name: stop_event))

    exit_code = main.request_stop()

    assert exit_code == 0
    assert stop_event.set_calls == 1


def test_request_stop_reports_missing_instance(paths, names, monkeypatch):
    errors: list[tuple[str, str]] = []

    monkeypatch.setattr(main.AppPaths, "discover", classmethod(lambda cls: paths))
    monkeypatch.setattr(main.InstanceNames, "for_data_root", classmethod(lambda cls, _root: names))
    monkeypatch.setattr(
        main.NamedEvent,
        "open",
        classmethod(lambda cls, _name: (_ for _ in ()).throw(OSError("missing"))),
    )

    exit_code = main.request_stop(
        show_error=lambda title, message: errors.append((title, message))
    )

    assert exit_code == 1
    assert errors == [("AzureSync", "AzureSync is not running.")]


def test_entrypoint_dispatches_by_frozen_executable_name(monkeypatch):
    monkeypatch.setattr(main, "launch", lambda: 41)
    monkeypatch.setattr(main, "request_stop", lambda: 7)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", os.fspath(Path("C:/Portable/StopAzureSync.exe")))

    assert main.entrypoint() == 7

    monkeypatch.setattr(sys, "executable", os.fspath(Path("C:/Portable/AzureSync.exe")))

    assert main.entrypoint() == 41
