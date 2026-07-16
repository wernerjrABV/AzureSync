import json
from unittest.mock import MagicMock

from scripts.backfill_assigned_to_display_name import extract_display_name, run


def test_extract_display_name_from_dict_field():
    raw = json.dumps(
        {"fields": {"System.AssignedTo": {"displayName": "Alice", "uniqueName": "alice@example.com"}}}
    )
    assert extract_display_name(raw) == "Alice"


def test_extract_display_name_returns_none_when_unassigned():
    raw = json.dumps({"fields": {}})
    assert extract_display_name(raw) is None


def test_extract_display_name_handles_string_field():
    raw = json.dumps({"fields": {"System.AssignedTo": "Bob"}})
    assert extract_display_name(raw) == "Bob"


def test_extract_display_name_returns_none_for_dict_without_display_name():
    raw = json.dumps({"fields": {"System.AssignedTo": {"uniqueName": "x@example.com"}}})
    assert extract_display_name(raw) is None


def _make_fake_conn(rows):
    """Build a MagicMock connection whose named (read) cursor iterates over
    `rows` (id, raw_json_dict, assigned_to) tuples, and whose unnamed (write)
    cursor records executed statements/params."""
    read_cursor = MagicMock()
    read_cursor.__iter__.return_value = iter(rows)
    read_cursor.__enter__.return_value = read_cursor
    read_cursor.__exit__.return_value = False

    write_cursor = MagicMock()
    write_cursor.__enter__.return_value = write_cursor
    write_cursor.__exit__.return_value = False

    conn = MagicMock()

    def cursor_side_effect(*args, **kwargs):
        if kwargs.get("name") or (args and args[0]):
            return read_cursor
        return write_cursor

    conn.cursor.side_effect = cursor_side_effect
    return conn, write_cursor


def test_run_updates_row_when_display_name_differs():
    rows = [
        (1, {"fields": {"System.AssignedTo": {"displayName": "Alice", "uniqueName": "alice@example.com"}}}, "alice@example.com"),
    ]
    conn, write_cursor = _make_fake_conn(rows)

    updated = run(conn)

    assert updated == 1
    write_cursor.execute.assert_called_once_with(
        "UPDATE work_items SET assigned_to = %s WHERE id = %s",
        ("Alice", 1),
    )
    conn.commit.assert_called()


def test_run_skips_row_when_display_name_already_matches():
    rows = [
        (2, {"fields": {"System.AssignedTo": {"displayName": "Alice", "uniqueName": "alice@example.com"}}}, "Alice"),
    ]
    conn, write_cursor = _make_fake_conn(rows)

    updated = run(conn)

    assert updated == 0
    write_cursor.execute.assert_not_called()


def test_run_returns_correct_updated_count_for_mixed_rows():
    rows = [
        (1, {"fields": {"System.AssignedTo": {"displayName": "Alice", "uniqueName": "alice@example.com"}}}, "alice@example.com"),
        (2, {"fields": {"System.AssignedTo": {"displayName": "Bob", "uniqueName": "bob@example.com"}}}, "Bob"),
        (3, {"fields": {"System.AssignedTo": {"displayName": "Carol", "uniqueName": "carol@example.com"}}}, "carol@example.com"),
    ]
    conn, write_cursor = _make_fake_conn(rows)

    updated = run(conn)

    assert updated == 2
    assert write_cursor.execute.call_count == 2
