from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    install_dir: Path
    sync_executable: Path
    api_executable: Path
    data_dir: Path
    database_path: Path
    log_dir: Path
    run_dir: Path
    stop_file: Path

    @classmethod
    def discover(
        cls,
        executable: str | Path | None = None,
        local_app_data: str | Path | None = None,
    ) -> "AppPaths":
        if executable is None:
            if getattr(sys, "frozen", False):
                executable = Path(sys.executable)
            else:
                executable = Path(__file__).resolve().parents[3] / "AzureSync.exe"
        executable_path = Path(executable)
        install_dir = executable_path.parent

        if local_app_data is None:
            local_app_data = os.environ.get("AZURESYNC_LOCAL_APP_DATA")
        if local_app_data is None:
            local_app_data = os.environ["LOCALAPPDATA"]
        mutable_root = Path(local_app_data) / "AzureSync"
        data_dir = mutable_root / "data"
        return cls(
            install_dir=install_dir,
            sync_executable=install_dir / "_services" / "sync-service" / "sync-service.exe",
            api_executable=install_dir / "_services" / "api-read" / "api-read.exe",
            data_dir=data_dir,
            database_path=data_dir / "azure_sync.sqlite3",
            log_dir=mutable_root / "logs",
            run_dir=mutable_root / "run",
            stop_file=mutable_root / "run" / "stop.request",
        )


@dataclass(frozen=True)
class InstanceNames:
    mutex: str
    stop_event: str

    @classmethod
    def for_data_root(cls, data_root: Path) -> "InstanceNames":
        suffix = hashlib.sha256(
            str(Path(data_root).resolve()).lower().encode("utf-8")
        ).hexdigest()[:16]
        return cls(
            mutex=fr"Local\AzureSync.Mutex.{suffix}",
            stop_event=fr"Local\AzureSync.Stop.{suffix}",
        )
