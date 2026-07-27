import datetime
from dataclasses import dataclass


FINAL_STATES = frozenset({"Closed", "Done", "Resolved"})
CANCELED_STATE = "Canceled"
DEVELOPMENT_TYPES = frozenset({"User Story", "Technical Story", "Bug"})
EXTENDED_TYPES = frozenset({"Feature", "Technical Feature", "Incident", "Problem"})
SUPPORTED_TYPES = DEVELOPMENT_TYPES | EXTENDED_TYPES

_DEVELOPMENT_BACKLOG_STATES = frozenset({"New", "Waiting Development"})
_DEVELOPMENT_DOWNSTREAM_STATES = frozenset(
    {
        "Development",
        "Waiting Code Review",
        "Code Review",
        "Waiting Tests",
        "Tests",
    }
) | FINAL_STATES
_EXTENDED_BACKLOG_STATES = frozenset({"New"})
_EXTENDED_UPSTREAM_STATES = frozenset(
    {"Requirements Analysis", "Waiting Technical Analysis"}
)
_EXTENDED_DOWNSTREAM_STATES = frozenset(
    {
        "Technical Analysis",
        "Waiting Development",
        "Development",
        "Waiting Quality Analysis",
        "Quality Analysis",
        "Waiting Review",
        "Review",
        "Waiting Deployment",
        "Deployment",
        "Waiting Validation",
        "Validation",
    }
) | FINAL_STATES


@dataclass(frozen=True)
class StatusInterval:
    work_item_id: int
    area_path_id: int
    revision: int
    work_item_type: str
    state: str
    started_at: datetime.datetime
    ended_at: datetime.datetime


def state_from_update(update: dict) -> str | None:
    fields = update.get("fields")
    if not isinstance(fields, dict):
        return None
    field = fields.get("System.State")
    if not isinstance(field, dict):
        return None
    state = field.get("newValue")
    return state if isinstance(state, str) and state else None


def state_category(work_item_type: str, state: str) -> str | None:
    if work_item_type in DEVELOPMENT_TYPES:
        if state in _DEVELOPMENT_BACKLOG_STATES:
            return "backlog"
        if state in _DEVELOPMENT_DOWNSTREAM_STATES:
            return "downstream"
    elif work_item_type in EXTENDED_TYPES:
        if state in _EXTENDED_BACKLOG_STATES:
            return "backlog"
        if state in _EXTENDED_UPSTREAM_STATES:
            return "upstream"
        if state in _EXTENDED_DOWNSTREAM_STATES:
            return "downstream"
    return None


def _parse_revised_date(value: object) -> datetime.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.strptime(
            value.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S"
        )
    except ValueError:
        return None


def _valid_revision(update: dict) -> int | None:
    revision = update.get("rev")
    return revision if isinstance(revision, int) and not isinstance(revision, bool) else None


def build_status_intervals(
    *,
    work_item_id: int,
    area_path_id: int,
    work_item_type: str,
    updates: list[dict],
) -> list[StatusInterval]:
    if work_item_type not in SUPPORTED_TYPES:
        return []

    if any(state_from_update(update) == CANCELED_STATE for update in updates):
        return []

    revisions: list[tuple[int, datetime.datetime, str]] = []
    for update in updates:
        revision = _valid_revision(update)
        revised_at = _parse_revised_date(update.get("revisedDate"))
        state = state_from_update(update)
        if revision is None or revised_at is None or state is None:
            continue
        revisions.append((revision, revised_at, state))

    revisions.sort(key=lambda item: item[0])
    intervals = []
    for index, (revision, started_at, state) in enumerate(revisions):
        ended_at = revisions[index + 1][1] if index + 1 < len(revisions) else started_at
        intervals.append(
            StatusInterval(
                work_item_id=work_item_id,
                area_path_id=area_path_id,
                revision=revision,
                work_item_type=work_item_type,
                state=state,
                started_at=started_at,
                ended_at=ended_at,
            )
        )
    return intervals
