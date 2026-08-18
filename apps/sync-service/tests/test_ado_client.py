import datetime
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.ado_client import AdoAuthError, AdoClient, AdoRetryExhaustedError
from app.credential_protection import CredentialProtectionError


def _response(status_code, json_body=None, headers=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.headers = headers or {}
    return resp


@patch("app.ado_client.requests.post")
def test_get_all_ids_uses_under_operator_when_subpaths_true(mock_post):
    mock_post.return_value = _response(200, {"workItems": [{"id": 1}, {"id": 2}]})

    client = AdoClient("org", "proj", pat="fake-pat")
    ids = client.get_all_ids("proj\\Team A", incluir_subpaths=True)

    assert ids == [1, 2]
    sent_query = mock_post.call_args.kwargs["json"]["query"]
    assert "UNDER 'proj\\Team A'" in sent_query


@patch("app.ado_client.requests.post")
def test_get_all_ids_uses_equals_operator_when_subpaths_false(mock_post):
    mock_post.return_value = _response(200, {"workItems": []})

    client = AdoClient("org", "proj", pat="fake-pat")
    client.get_all_ids("proj\\Team A", incluir_subpaths=False)

    sent_query = mock_post.call_args.kwargs["json"]["query"]
    assert "[System.AreaPath] = 'proj\\Team A'" in sent_query


@patch("app.ado_client.requests.post")
def test_get_changed_ids_includes_changed_date_filter(mock_post):
    mock_post.return_value = _response(200, {"workItems": []})

    client = AdoClient("org", "proj", pat="fake-pat")
    since = datetime.datetime(2026, 7, 1, 12, 0, 0)
    client.get_changed_ids("proj\\Team A", incluir_subpaths=True, since=since)

    sent_query = mock_post.call_args.kwargs["json"]["query"]
    assert "[System.ChangedDate] >= '2026-07-01'" in sent_query


@patch("app.ado_client.requests.post")
def test_get_changed_ids_without_since_has_no_date_filter(mock_post):
    mock_post.return_value = _response(200, {"workItems": []})

    client = AdoClient("org", "proj", pat="fake-pat")
    client.get_changed_ids("proj\\Team A", incluir_subpaths=True, since=None)

    sent_query = mock_post.call_args.kwargs["json"]["query"]
    assert "ChangedDate" not in sent_query


@patch("app.ado_client.requests.post")
def test_get_work_items_batch_maps_fields(mock_post):
    mock_post.return_value = _response(
        200,
        {
            "value": [
                {
                    "id": 1,
                    "fields": {
                        "System.Title": "Bug A",
                        "System.WorkItemType": "Bug",
                        "System.State": "Active",
                        "System.AssignedTo": {"displayName": "Alice", "uniqueName": "alice@example.com"},
                        "System.ChangedDate": "2026-07-01T12:00:00Z",
                        "Custom.Squad": "Platform",
                    },
                }
            ]
        },
    )

    client = AdoClient("org", "proj", pat="fake-pat")
    items = client.get_work_items_batch([1])

    assert len(items) == 1
    item = items[0]
    assert item["id"] == 1
    assert item["title"] == "Bug A"
    assert item["work_item_type"] == "Bug"
    assert item["state"] == "Active"
    assert item["assigned_to"] == "Alice"
    assert item["changed_date"] == datetime.datetime(2026, 7, 1, 12, 0, 0)
    raw = json.loads(item["raw_json"])
    assert raw["id"] == 1
    assert raw["fields"]["Custom.Squad"] == "Platform"


@patch("app.ado_client.requests.post")
def test_get_work_items_batch_requests_all_fields_via_expand(mock_post):
    mock_post.return_value = _response(200, {"value": []})

    client = AdoClient("org", "proj", pat="fake-pat")
    client.get_work_items_batch([1])

    sent_body = mock_post.call_args.kwargs["json"]
    assert sent_body["$expand"] == "all"
    assert "fields" not in sent_body


@patch("app.ado_client.requests.post")
def test_401_raises_auth_error_without_retry(mock_post):
    mock_post.return_value = _response(401)

    client = AdoClient("org", "proj", pat="bad-pat")
    with pytest.raises(AdoAuthError):
        client.get_all_ids("proj\\A", incluir_subpaths=True)

    assert mock_post.call_count == 1


@patch("app.ado_client.time.sleep")
@patch("app.ado_client.requests.post")
def test_429_retries_with_fixed_delays_then_succeeds(mock_post, mock_sleep):
    mock_post.side_effect = [
        _response(429),
        _response(429),
        _response(200, {"workItems": [{"id": 1}]}),
    ]

    client = AdoClient("org", "proj", pat="fake-pat")
    ids = client.get_all_ids("proj\\A", incluir_subpaths=True)

    assert ids == [1]
    assert mock_sleep.call_args_list == [((5,),), ((15,),)]


@patch("app.ado_client.time.sleep")
@patch("app.ado_client.requests.post")
def test_429_exhausts_retries_and_raises(mock_post, mock_sleep):
    mock_post.side_effect = [_response(429), _response(429), _response(429)]

    client = AdoClient("org", "proj", pat="fake-pat")
    with pytest.raises(AdoRetryExhaustedError):
        client.get_all_ids("proj\\A", incluir_subpaths=True)

    assert mock_sleep.call_args_list == [((5,),), ((15,),), ((30,),)]


@patch("app.ado_client.time.sleep")
@patch("app.ado_client.requests.post")
def test_retry_after_header_overrides_default_delay(mock_post, mock_sleep):
    mock_post.side_effect = [
        _response(429, headers={"Retry-After": "20"}),
        _response(200, {"workItems": []}),
    ]

    client = AdoClient("org", "proj", pat="fake-pat")
    client.get_all_ids("proj\\A", incluir_subpaths=True)

    mock_sleep.assert_called_once_with(20)


@patch("app.ado_client.requests.get")
def test_get_work_item_updates_single_page(mock_get):
    page1 = {
        "value": [
            {
                "id": 1,
                "rev": 2,
                "revisedBy": {"uniqueName": "alice@example.com"},
                "revisedDate": "2026-07-01T12:00:00Z",
                "fields": {"System.State": {"oldValue": "New", "newValue": "Active"}},
            }
        ]
    }
    mock_get.side_effect = [_response(200, page1), _response(200, {"value": []})]

    client = AdoClient("org", "proj", pat="fake-pat")
    updates = client.get_work_item_updates(42)

    assert len(updates) == 1
    assert updates[0]["rev"] == 2
    sent_url = mock_get.call_args.args[0]
    assert "workitems/42/updates" in sent_url
    assert "api-version=7.1" in sent_url


@patch("app.ado_client.requests.get")
def test_get_work_item_updates_paginates_until_empty_page(mock_get):
    page1 = {"value": [{"id": 1, "rev": i} for i in range(100)]}
    page2 = {"value": [{"id": 1, "rev": 100}]}
    page3 = {"value": []}
    mock_get.side_effect = [_response(200, page1), _response(200, page2), _response(200, page3)]

    client = AdoClient("org", "proj", pat="fake-pat")
    updates = client.get_work_item_updates(42)

    assert len(updates) == 101
    assert mock_get.call_count == 3
    skips = [call.kwargs.get("params", {}).get("$skip") for call in mock_get.call_args_list]
    assert skips == [0, 100, 200]


@patch("app.ado_client.requests.get")
def test_get_work_item_updates_401_raises_auth_error(mock_get):
    mock_get.return_value = _response(401)

    client = AdoClient("org", "proj", pat="bad-pat")
    with pytest.raises(AdoAuthError):
        client.get_work_item_updates(42)


@patch("app.ado_client.time.sleep")
@patch("app.ado_client.requests.get")
def test_get_work_item_updates_retries_on_429(mock_get, mock_sleep):
    mock_get.side_effect = [
        _response(429),
        _response(200, {"value": []}),
    ]

    client = AdoClient("org", "proj", pat="fake-pat")
    updates = client.get_work_item_updates(42)

    assert updates == []
    mock_sleep.assert_called_once_with(5)


@patch("app.ado_client.requests.post")
def test_get_work_items_batch_extracts_start_and_target_dates(mock_post):
    mock_post.return_value = _response(
        200,
        {
            "value": [
                {
                    "id": 1,
                    "fields": {
                        "System.Title": "Feature A",
                        "System.WorkItemType": "Feature",
                        "System.State": "Active",
                        "System.ChangedDate": "2026-07-01T12:00:00Z",
                        "Microsoft.VSTS.Scheduling.StartDate": "2026-01-10T00:00:00Z",
                        "Microsoft.VSTS.Scheduling.TargetDate": "2026-02-28T00:00:00Z",
                    },
                }
            ]
        },
    )

    client = AdoClient("org", "proj", pat="fake-pat")
    items = client.get_work_items_batch([1])

    item = items[0]
    assert item["start_date"] == datetime.datetime(2026, 1, 10, 0, 0, 0)
    assert item["target_date"] == datetime.datetime(2026, 2, 28, 0, 0, 0)


@patch("app.ado_client.requests.post")
def test_get_work_items_batch_handles_missing_scheduling_dates(mock_post):
    mock_post.return_value = _response(
        200,
        {
            "value": [
                {
                    "id": 2,
                    "fields": {
                        "System.Title": "Bug B",
                        "System.WorkItemType": "Bug",
                        "System.State": "Active",
                        "System.ChangedDate": "2026-07-01T12:00:00Z",
                    },
                }
            ]
        },
    )

    client = AdoClient("org", "proj", pat="fake-pat")
    items = client.get_work_items_batch([2])

    item = items[0]
    assert item["start_date"] is None
    assert item["target_date"] is None


@patch("app.ado_client.requests.post")
def test_get_work_items_batch_extracts_created_activated_closed_dates(mock_post):
    mock_post.return_value = _response(
        200,
        {
            "value": [
                {
                    "id": 1,
                    "fields": {
                        "System.Title": "Feature A",
                        "System.WorkItemType": "Feature",
                        "System.State": "Closed",
                        "System.ChangedDate": "2026-07-01T12:00:00Z",
                        "System.CreatedDate": "2025-11-01T09:00:00Z",
                        "Microsoft.VSTS.Common.ActivatedDate": "2025-12-01T09:00:00Z",
                        "Microsoft.VSTS.Common.ClosedDate": "2026-06-15T17:30:00Z",
                    },
                }
            ]
        },
    )

    client = AdoClient("org", "proj", pat="fake-pat")
    items = client.get_work_items_batch([1])

    item = items[0]
    assert item["created_date"] == datetime.datetime(2025, 11, 1, 9, 0, 0)
    assert item["activated_date"] == datetime.datetime(2025, 12, 1, 9, 0, 0)
    assert item["closed_date"] == datetime.datetime(2026, 6, 15, 17, 30, 0)


@patch("app.ado_client.requests.post")
def test_get_work_items_batch_handles_missing_created_activated_closed_dates(mock_post):
    mock_post.return_value = _response(
        200,
        {
            "value": [
                {
                    "id": 2,
                    "fields": {
                        "System.Title": "Bug B",
                        "System.WorkItemType": "Bug",
                        "System.State": "Active",
                        "System.ChangedDate": "2026-07-01T12:00:00Z",
                    },
                }
            ]
        },
    )

    client = AdoClient("org", "proj", pat="fake-pat")
    items = client.get_work_items_batch([2])

    item = items[0]
    assert item["created_date"] is None
    assert item["activated_date"] is None
    assert item["closed_date"] is None


def test_auth_resolves_and_caches_pat_from_provider():
    provider = MagicMock(return_value="stored-pat")

    client = AdoClient("org", "project", pat_provider=provider)

    assert client._auth() == ("", "stored-pat")
    assert client._auth() == ("", "stored-pat")
    provider.assert_called_once_with()


def test_auth_reports_missing_credential_without_reading_environment():
    client = AdoClient("org", "project", pat_provider=lambda: None)

    with pytest.raises(AdoAuthError, match="not configured"):
        client._auth()


def test_auth_wraps_protection_failure_without_secret_material():
    def fail():
        raise CredentialProtectionError("stored credential cannot be decrypted")

    with pytest.raises(AdoAuthError, match="cannot be decrypted") as error:
        AdoClient("org", "project", pat_provider=fail)._auth()

    assert "api_key" not in str(error.value).lower()
