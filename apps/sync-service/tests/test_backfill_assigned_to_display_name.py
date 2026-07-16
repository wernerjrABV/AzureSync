import json

from scripts.backfill_assigned_to_display_name import extract_display_name


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
