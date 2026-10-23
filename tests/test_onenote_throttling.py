"""Tests for Graph throttling (HTTP 429) handling in the OneNote client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.integrations.outlook.client import OutlookClient


def _response(status=200, json_data=None, text="", headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.text = text
    resp.json.return_value = json_data or {}
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status} Client Error")
    return resp


@pytest.fixture
def client():
    return OutlookClient("token")


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("src.integrations.outlook.client.time.sleep") as sleep:
        yield sleep


def test_retries_after_429_and_honours_retry_after(client, no_sleep):
    responses = [_response(429, headers={"Retry-After": "2"}), _response(200, text="<p>hi</p>")]
    with patch("src.integrations.outlook.client.requests.get", side_effect=responses) as get:
        assert client.get_page_content("page-1") == "<p>hi</p>"
    assert get.call_count == 2
    no_sleep.assert_called_once_with(2.0)


def test_backs_off_exponentially_without_retry_after(client, no_sleep):
    responses = [_response(429), _response(429), _response(200, text="ok")]
    with patch("src.integrations.outlook.client.requests.get", side_effect=responses):
        assert client.get_page_content("page-1") == "ok"
    assert [c.args[0] for c in no_sleep.call_args_list] == [1.0, 2.0]


def test_gives_up_after_max_retries(client):
    responses = [_response(429)] * 4
    with patch("src.integrations.outlook.client.requests.get", side_effect=responses) as get:
        with pytest.raises(requests.HTTPError):
            client.get_page_content("page-1")
    assert get.call_count == 4


def test_list_pages_survives_throttled_page_content(client):
    listing = _response(200, json_data={"value": [{"id": "a"}, {"id": "b"}]})
    # Page "a" is throttled on every attempt; page "b" succeeds.
    responses = [listing] + [_response(429)] * 4 + [_response(200, text="<p>b</p>")]
    with patch("src.integrations.outlook.client.requests.get", side_effect=responses):
        pages = client.list_pages(include_content=True)
    assert pages[0]["content"] is None
    assert pages[1]["content"] == "<p>b</p>"
