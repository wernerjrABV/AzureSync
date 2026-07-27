import datetime

from app.capacity import build_status_intervals, state_category


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
