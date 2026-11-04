import pytest
import requests

import api_request


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


def test_mock_fetch_data_shape():
    data = api_request.mock_fetch_data()
    assert data["location"]["name"] == "New York"
    assert data["location"]["utc_offset"] == "-4.0"
    assert isinstance(data["current"]["temperature"], int)
    assert data["current"]["weather_descriptions"]


def test_fetch_data_requires_api_key(monkeypatch):
    monkeypatch.delenv("WEATHERSTACK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="WEATHERSTACK_API_KEY"):
        api_request.fetch_data()


def test_fetch_data_passes_timeout_and_env(monkeypatch):
    monkeypatch.setenv("WEATHERSTACK_API_KEY", "k")
    monkeypatch.setenv("WEATHER_CITY", "Paris")
    calls = {}

    def fake_get(url, **kwargs):
        calls["url"] = url
        calls.update(kwargs)
        return FakeResponse({"current": {}})

    monkeypatch.setattr(api_request.requests, "get", fake_get)
    assert api_request.fetch_data() == {"current": {}}
    assert calls["timeout"] == (5, 30)
    assert calls["params"] == {"access_key": "k", "query": "Paris"}


def test_fetch_data_raises_on_success_false(monkeypatch):
    monkeypatch.setenv("WEATHERSTACK_API_KEY", "k")
    payload = {"success": False, "error": {"code": 104, "info": "quota"}}
    monkeypatch.setattr(api_request.requests, "get", lambda *a, **kw: FakeResponse(payload))
    with pytest.raises(RuntimeError, match="Weatherstack API error"):
        api_request.fetch_data()


def test_fetch_data_propagates_http_error(monkeypatch):
    monkeypatch.setenv("WEATHERSTACK_API_KEY", "k")
    monkeypatch.setattr(api_request.requests, "get", lambda *a, **kw: FakeResponse({}, 500))
    with pytest.raises(requests.exceptions.HTTPError):
        api_request.fetch_data()
