from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
MB_OK = 0x00000000
MB_ICONERROR = 0x00000010

kernel32 = None
_message_box = None
if sys.platform == "win32":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.SetEvent.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, wintypes.INT, wintypes.LPVOID, wintypes.DWORD]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _message_box = _user32.MessageBoxW
    _message_box.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
    _message_box.restype = ctypes.c_int


def _require_windows() -> None:
    if kernel32 is None:
        raise OSError("Windows launcher primitives require Windows")


def _raise_last_error(message: str) -> None:
    error = ctypes.get_last_error()
    raise OSError(error, f"{message} (Win32 error {error})")


class _Handle:
    def __init__(self, handle):
        self._handle = handle

    def close(self) -> None:
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()


class NamedMutex(_Handle):
    @classmethod
    def acquire(cls, name: str) -> tuple["NamedMutex", bool]:
        _require_windows()
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            _raise_last_error("CreateMutexW failed")
        return cls(handle), ctypes.get_last_error() != ERROR_ALREADY_EXISTS


class NamedEvent(_Handle):
    @classmethod
    def create(cls, name: str) -> "NamedEvent":
        _require_windows()
        handle = kernel32.CreateEventW(None, True, False, name)
        if not handle:
            _raise_last_error("CreateEventW failed")
        return cls(handle)

    @classmethod
    def open(cls, name: str) -> "NamedEvent":
        _require_windows()
        handle = kernel32.OpenEventW(EVENT_MODIFY_STATE | SYNCHRONIZE, False, name)
        if not handle:
            _raise_last_error("OpenEventW failed")
        return cls(handle)

    def set(self) -> None:
        if not self._handle or not kernel32.SetEvent(self._handle):
            _raise_last_error("SetEvent failed")

    def wait(self, timeout_ms: int) -> bool:
        if not self._handle:
            raise ValueError("event is closed")
        result = kernel32.WaitForSingleObject(self._handle, timeout_ms)
        if result == WAIT_OBJECT_0:
            return True
        if result == WAIT_TIMEOUT:
            return False
        _raise_last_error("WaitForSingleObject failed")


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_void_p), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [("ReadOperationCount", ctypes.c_uint64), ("WriteOperationCount", ctypes.c_uint64), ("OtherOperationCount", ctypes.c_uint64), ("ReadTransferCount", ctypes.c_uint64), ("WriteTransferCount", ctypes.c_uint64), ("OtherTransferCount", ctypes.c_uint64)]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimitInformation), ("IoInfo", _IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class KillOnCloseJob(_Handle):
    @classmethod
    def create(cls) -> "KillOnCloseJob":
        _require_windows()
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            _raise_last_error("CreateJobObjectW failed")
        info = _ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(handle)
            _raise_last_error("SetInformationJobObject failed")
        return cls(handle)

    def assign(self, process_handle) -> None:
        if not self._handle or not kernel32.AssignProcessToJobObject(self._handle, process_handle):
            _raise_last_error("AssignProcessToJobObject failed")


def show_error(title: str, message: str) -> None:
    if _message_box is None:
        return
    _message_box(None, message, title, MB_ICONERROR | MB_OK)
