import sys
import uuid

import pytest

from azuresync_launcher.windows_control import (
    KillOnCloseJob,
    NamedEvent,
    NamedMutex,
    show_error,
)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher only")
def test_named_mutex_reports_second_acquisition():
    name = rf"Local\AzureSync.Test.{uuid.uuid4()}"
    first, first_created = NamedMutex.acquire(name)
    second, second_created = NamedMutex.acquire(name)
    try:
        assert first_created is True
        assert second_created is False
    finally:
        second.close()
        first.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher only")
def test_named_event_can_be_opened_and_signaled():
    name = rf"Local\AzureSync.Stop.Test.{uuid.uuid4()}"
    owner = NamedEvent.create(name)
    observer = NamedEvent.open(name)
    try:
        assert observer.wait(0) is False
        owner.set()
        assert observer.wait(1000) is True
    finally:
        observer.close()
        owner.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher only")
def test_job_kills_assigned_process():
    import subprocess

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    job = KillOnCloseJob.create()
    try:
        job.assign(child._handle)
        job.close()
        child.wait(timeout=5)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_show_error_uses_message_box(monkeypatch):
    import azuresync_launcher.windows_control as control

    calls = []
    monkeypatch.setattr(control, "_message_box", lambda hwnd, message, title, flags: calls.append((message, title, flags)))
    show_error("Title", "Message")
    assert calls == [("Message", "Title", control.MB_ICONERROR | control.MB_OK)]
