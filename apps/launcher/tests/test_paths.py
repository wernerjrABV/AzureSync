import sys
from pathlib import Path

from azuresync_launcher.paths import AppPaths, InstanceNames


def test_discovers_install_services_and_mutable_paths(tmp_path):
    install = tmp_path / "AzureSync-win-x64"
    executable = install / "AzureSync.exe"
    local = tmp_path / "LocalAppData"

    paths = AppPaths.discover(executable=executable, local_app_data=local)

    assert paths.install_dir == install
    assert paths.sync_executable == install / "_services" / "sync-service" / "sync-service.exe"
    assert paths.api_executable == install / "_services" / "api-read" / "api-read.exe"
    assert paths.data_dir == local / "AzureSync" / "data"
    assert paths.database_path == local / "AzureSync" / "data" / "azure_sync.sqlite3"
    assert paths.log_dir == local / "AzureSync" / "logs"
    assert paths.run_dir == local / "AzureSync" / "run"
    assert paths.stop_file == local / "AzureSync" / "run" / "stop.request"


def test_non_frozen_discovery_defaults_to_repository_install_root(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    paths = AppPaths.discover()

    assert paths.install_dir == Path(__file__).resolve().parents[3]
    assert paths.install_dir.name == "AzureSync"
    assert paths.sync_executable == paths.install_dir / "_services" / "sync-service" / "sync-service.exe"


def test_instance_names_are_stable_and_do_not_include_data_root(tmp_path):
    root = tmp_path / "LocalAppData" / "AzureSync"
    names = InstanceNames.for_data_root(root)
    assert names == InstanceNames.for_data_root(root)
    assert str(root).lower() not in names.mutex.lower()
    assert names.mutex.startswith(r"Local\AzureSync.Mutex.")
    assert names.stop_event.startswith(r"Local\AzureSync.Stop.")
