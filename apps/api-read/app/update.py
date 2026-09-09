from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path


REPOSITORY = "wernerjrABV/AzureSync"
BRANCH = "main"
ROOT = Path(__file__).resolve().parents[3]
VERSION_PATH = ROOT / "VERSION"
REMOTE_VERSION_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/{BRANCH}/VERSION"


def current_version() -> str:
    return VERSION_PATH.read_text(encoding="utf-8").strip()


def check_for_update(urlopen=urllib.request.urlopen) -> dict[str, object]:
    installed = current_version()
    try:
        with urlopen(REMOTE_VERSION_URL, timeout=3) as response:
            latest = response.read().decode("utf-8").strip()
    except Exception:
        return {"update_available": False, "current_version": installed, "latest_version": None}
    return {
        "update_available": bool(latest and latest != installed),
        "current_version": installed,
        "latest_version": latest or None,
    }


def start_update(popen=subprocess.Popen) -> None:
    update_script = ROOT / "scripts" / "update.ps1"
    popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(update_script),
            "-InstallRoot",
            str(ROOT),
        ],
        cwd=ROOT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        close_fds=True,
    )
