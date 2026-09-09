import threading


_EVENTS: dict[int, threading.Event] = {}
_LOCK = threading.Lock()


def register(area_path_id: int) -> threading.Event:
    with _LOCK:
        return _EVENTS.setdefault(area_path_id, threading.Event())


def cancel(area_path_id: int) -> bool:
    with _LOCK:
        event = _EVENTS.get(area_path_id)
        if event is None:
            return False
        event.set()
        return True


def get(area_path_id: int) -> threading.Event | None:
    with _LOCK:
        return _EVENTS.get(area_path_id)


def cancel_all() -> int:
    with _LOCK:
        for event in _EVENTS.values():
            event.set()
        return len(_EVENTS)


def unregister(area_path_id: int) -> None:
    with _LOCK:
        _EVENTS.pop(area_path_id, None)
