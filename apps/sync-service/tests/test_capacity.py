import datetime

from app.capacity import StatusInterval, build_capacity_snapshot, build_status_intervals, state_category


def dt(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


def update(revision: int, revised_date: str, state: str | None) -> dict:
    fields = {} if state is None else {"System.State": {"newValue": state}}
    return {"rev": revision, "revisedDate": revised_date, "fields": fields}


def test_build_status_intervals_closes_each_state_at_next_revision():
    intervals = build_status_intervals(
        work_item_id=17,
        area_path_id=3,
        work_item_type="User Story",
        updates=[
            update(1, "2026-01-01T09:00:00Z", "New"),
            update(2, "2026-01-02T09:00:00Z", "Development"),
            update(3, "2026-01-04T09:00:00Z", "Waiting Code Review"),
            update(4, "2026-01-05T09:00:00Z", "Development"),
            update(5, "2026-01-06T09:00:00Z", "Closed"),
        ],
    )

    assert [(item.revision, item.state, item.started_at, item.ended_at) for item in intervals] == [
        (1, "New", dt("2026-01-01T09:00:00"), dt("2026-01-02T09:00:00")),
        (2, "Development", dt("2026-01-02T09:00:00"), dt("2026-01-04T09:00:00")),
        (3, "Waiting Code Review", dt("2026-01-04T09:00:00"), dt("2026-01-05T09:00:00")),
        (4, "Development", dt("2026-01-05T09:00:00"), dt("2026-01-06T09:00:00")),
        (5, "Closed", dt("2026-01-06T09:00:00"), dt("2026-01-06T09:00:00")),
    ]


def test_build_status_intervals_preserves_repeated_states_as_distinct_intervals():
    intervals = build_status_intervals(
        work_item_id=17,
        area_path_id=3,
        work_item_type="Bug",
        updates=[
            update(3, "2026-01-03T09:00:00Z", "Development"),
            update(1, "2026-01-01T09:00:00Z", "New"),
            update(2, "2026-01-02T09:00:00Z", "Development"),
        ],
    )

    assert [(item.revision, item.state) for item in intervals] == [
        (1, "New"),
        (2, "Development"),
        (3, "Development"),
    ]


def test_build_status_intervals_keeps_reopened_final_state_history():
    intervals = build_status_intervals(
        work_item_id=17,
        area_path_id=3,
        work_item_type="Technical Story",
        updates=[
            update(1, "2026-01-01T09:00:00Z", "Development"),
            update(2, "2026-01-03T09:00:00Z", "Closed"),
            update(3, "2026-01-05T09:00:00Z", "Development"),
            update(4, "2026-01-07T09:00:00Z", "Closed"),
        ],
    )

    assert [(item.state, item.started_at, item.ended_at) for item in intervals] == [
        ("Development", dt("2026-01-01T09:00:00"), dt("2026-01-03T09:00:00")),
        ("Closed", dt("2026-01-03T09:00:00"), dt("2026-01-05T09:00:00")),
        ("Development", dt("2026-01-05T09:00:00"), dt("2026-01-07T09:00:00")),
        ("Closed", dt("2026-01-07T09:00:00"), dt("2026-01-07T09:00:00")),
    ]


def test_build_status_intervals_excludes_item_that_reaches_canceled():
    intervals = build_status_intervals(
        work_item_id=17,
        area_path_id=3,
        work_item_type="User Story",
        updates=[
            update(1, "2026-01-01T09:00:00Z", "New"),
            update(2, "2026-01-02T09:00:00Z", "Canceled"),
        ],
    )

    assert intervals == []


def test_build_status_intervals_ignores_malformed_revisions():
    intervals = build_status_intervals(
        work_item_id=17,
        area_path_id=3,
        work_item_type="User Story",
        updates=[
            update(1, "not-a-date", "New"),
            update(2, "2026-01-02T09:00:00Z", None),
            update(3, "2026-01-03T09:00:00Z", "Development"),
        ],
    )

    assert [(item.revision, item.state, item.started_at, item.ended_at) for item in intervals] == [
        (3, "Development", dt("2026-01-03T09:00:00"), dt("2026-01-03T09:00:00")),
    ]


def test_state_category_places_technical_analysis_downstream_for_extended_types():
    assert state_category("Feature", "Technical Analysis") == "downstream"


def interval(
    work_item_id: int, work_item_type: str, state: str, started_at: str, ended_at: str
) -> StatusInterval:
    return StatusInterval(
        work_item_id=work_item_id,
        area_path_id=3,
        revision=1,
        work_item_type=work_item_type,
        state=state,
        started_at=dt(started_at),
        ended_at=dt(ended_at),
    )


def closed_story_intervals_for_monthly_counts(counts: list[int]) -> list[StatusInterval]:
    intervals = []
    item_id = 1
    for month, count in zip(("2026-05", "2026-06", "2026-07"), counts):
        for day in range(1, count + 1):
            completed_at = f"{month}-{day:02d}T09:00:00"
            intervals.append(
                interval(item_id, "User Story", "Closed", completed_at, completed_at)
            )
            item_id += 1
    return intervals


def test_snapshot_uses_last_final_completion_and_quarterly_percentiles():
    snapshot = build_capacity_snapshot(
        area_path_id=3,
        intervals=closed_story_intervals_for_monthly_counts([2, 4, 6]),
        as_of=dt("2026-07-27T00:00:00"),
    )

    story = snapshot["by_type"]["User Story"]
    assert story["forecast"] == {"conservative": 6, "expected": 12, "optimistic": 18}
    assert story["is_reliable"] is True


def test_snapshot_includes_exactly_twelve_zero_filled_calendar_months():
    snapshot = build_capacity_snapshot(
        area_path_id=3,
        intervals=closed_story_intervals_for_monthly_counts([2, 4, 6]),
        as_of=dt("2026-07-27T00:00:00"),
    )

    assert snapshot["monthly_throughput"] == [
        {"month": "2025-08", "count": 0},
        {"month": "2025-09", "count": 0},
        {"month": "2025-10", "count": 0},
        {"month": "2025-11", "count": 0},
        {"month": "2025-12", "count": 0},
        {"month": "2026-01", "count": 0},
        {"month": "2026-02", "count": 0},
        {"month": "2026-03", "count": 0},
        {"month": "2026-04", "count": 0},
        {"month": "2026-05", "count": 2},
        {"month": "2026-06", "count": 4},
        {"month": "2026-07", "count": 6},
    ]


def test_snapshot_marks_type_unreliable_with_fewer_than_three_delivery_months():
    snapshot = build_capacity_snapshot(
        area_path_id=3,
        intervals=closed_story_intervals_for_monthly_counts([0, 2, 4]),
        as_of=dt("2026-07-27T00:00:00"),
    )

    assert snapshot["by_type"]["User Story"]["is_reliable"] is False
    assert snapshot["is_reliable"] is False


def test_snapshot_calculates_forecasts_independently_per_work_item_type():
    snapshot = build_capacity_snapshot(
        area_path_id=3,
        intervals=(
            closed_story_intervals_for_monthly_counts([2, 4, 6])
            + [
                interval(100, "Bug", "Closed", "2026-05-01T09:00:00", "2026-05-01T09:00:00"),
                interval(101, "Bug", "Closed", "2026-06-01T09:00:00", "2026-06-01T09:00:00"),
                interval(102, "Bug", "Closed", "2026-07-01T09:00:00", "2026-07-01T09:00:00"),
            ]
        ),
        as_of=dt("2026-07-27T00:00:00"),
    )

    assert snapshot["by_type"]["User Story"]["forecast"]["expected"] == 12
    assert snapshot["by_type"]["Bug"]["forecast"]["expected"] == 3


def test_snapshot_counts_reopened_item_only_at_its_last_final_transition():
    snapshot = build_capacity_snapshot(
        area_path_id=3,
        intervals=[
            interval(17, "User Story", "Closed", "2026-05-02T09:00:00", "2026-05-02T09:00:00"),
            interval(17, "User Story", "Development", "2026-05-02T09:00:00", "2026-07-10T09:00:00"),
            interval(17, "User Story", "Closed", "2026-07-10T09:00:00", "2026-07-10T09:00:00"),
        ],
        as_of=dt("2026-07-27T00:00:00"),
    )

    counts = {bucket["month"]: bucket["count"] for bucket in snapshot["monthly_throughput"]}
    assert counts["2026-05"] == 0
    assert counts["2026-07"] == 1
