import datetime
import math
import statistics
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


def _month_starts_ending_at(as_of: datetime.datetime) -> list[datetime.datetime]:
    month = as_of.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    months = []
    for _ in range(12):
        months.append(month)
        month = (month - datetime.timedelta(days=1)).replace(day=1)
    return list(reversed(months))


def _month_key(value: datetime.datetime) -> str:
    return value.strftime("%Y-%m")


def _forecast(monthly_counts: list[int]) -> dict[str, int]:
    deliveries = sorted(count for count in monthly_counts if count > 0)
    if not deliveries:
        return {"conservative": 0, "expected": 0, "optimistic": 0}

    def percentile(percent: float) -> int:
        return deliveries[math.ceil(percent * len(deliveries)) - 1]

    return {
        "conservative": math.floor(percentile(0.25) * 3),
        "expected": math.floor(percentile(0.50) * 3),
        "optimistic": math.floor(percentile(0.75) * 3),
    }


def _throughput_buckets(months: list[datetime.datetime], counts: dict[str, int]) -> list[dict]:
    return [{"month": _month_key(month), "count": counts.get(_month_key(month), 0)} for month in months]


def _flow_metrics(intervals: list[StatusInterval]) -> dict[str, dict]:
    by_type: dict[str, list[StatusInterval]] = {}
    for item in intervals:
        by_type.setdefault(item.work_item_type, []).append(item)

    result = {}
    for work_item_type, type_intervals in by_type.items():
        duration_by_state: dict[str, list[float]] = {}
        for item in type_intervals:
            duration_by_state.setdefault(item.state, []).append(
                (item.ended_at - item.started_at).total_seconds()
            )

        median_by_state = {
            state: statistics.median(durations)
            for state, durations in sorted(duration_by_state.items())
        }
        upstream_seconds = sum(
            duration
            for state, duration in median_by_state.items()
            if state_category(work_item_type, state) == "upstream"
        )
        downstream_seconds = sum(
            duration
            for state, duration in median_by_state.items()
            if state_category(work_item_type, state) == "downstream"
        )
        result[work_item_type] = {
            "by_status": median_by_state,
            "upstream_seconds": upstream_seconds,
            "downstream_seconds": downstream_seconds,
            "development_cycle_seconds": upstream_seconds + downstream_seconds,
        }
    return result


def build_capacity_snapshot(
    *,
    area_path_id: int,
    intervals: list[StatusInterval],
    as_of: datetime.datetime,
) -> dict:
    """Build a JSON-safe twelve-month capacity snapshot for one Area Path."""
    area_intervals = [item for item in intervals if item.area_path_id == area_path_id]
    months = _month_starts_ending_at(as_of)
    month_keys = {_month_key(month) for month in months}

    last_completions: dict[int, StatusInterval] = {}
    for item in area_intervals:
        if (
            item.state not in FINAL_STATES
            or item.started_at != item.ended_at
            or item.ended_at > as_of
        ):
            continue
        previous = last_completions.get(item.work_item_id)
        if previous is None or (item.ended_at, item.revision) > (
            previous.ended_at,
            previous.revision,
        ):
            last_completions[item.work_item_id] = item

    counts_by_type: dict[str, dict[str, int]] = {}
    total_counts: dict[str, int] = {}
    for item in last_completions.values():
        month = _month_key(item.ended_at)
        if month not in month_keys:
            continue
        counts = counts_by_type.setdefault(item.work_item_type, {})
        counts[month] = counts.get(month, 0) + 1
        total_counts[month] = total_counts.get(month, 0) + 1

    by_type = {}
    warnings = []
    for work_item_type, counts in sorted(counts_by_type.items()):
        monthly_throughput = _throughput_buckets(months, counts)
        monthly_counts = [bucket["count"] for bucket in monthly_throughput]
        delivery_months = sum(count > 0 for count in monthly_counts)
        is_reliable = delivery_months >= 3
        by_type[work_item_type] = {
            "monthly_throughput": monthly_throughput,
            "forecast": _forecast(monthly_counts),
            "delivery_months": delivery_months,
            "is_reliable": is_reliable,
        }
        if not is_reliable:
            warnings.append(
                {
                    "code": "insufficient_delivery_history",
                    "work_item_type": work_item_type,
                    "message": "At least three non-zero delivery months are required for a reliable forecast.",
                }
            )

    monthly_throughput = _throughput_buckets(months, total_counts)
    total_monthly_counts = [bucket["count"] for bucket in monthly_throughput]
    delivery_months = sum(count > 0 for count in total_monthly_counts)
    is_reliable = delivery_months >= 3
    if not is_reliable:
        warnings.append(
            {
                "code": "insufficient_delivery_history",
                "message": "At least three non-zero delivery months are required for a reliable forecast.",
            }
        )

    history_start = min((item.started_at for item in area_intervals), default=None)
    return {
        "generated_at": as_of.isoformat(),
        "history_start": history_start.isoformat() if history_start else None,
        "monthly_throughput": monthly_throughput,
        "by_type": by_type,
        "forecast": _forecast(total_monthly_counts),
        "flow_metrics": _flow_metrics(area_intervals),
        "warnings": warnings,
        "delivery_months": delivery_months,
        "is_reliable": is_reliable,
    }
