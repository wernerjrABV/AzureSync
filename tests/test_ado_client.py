import datetime
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.ado_client import AdoAuthError, AdoClient, AdoRetryExhaustedError


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
    assert item["assigned_to"] == "alice@example.com"
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
    assert sent_body["$expand"] == "fields"
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
