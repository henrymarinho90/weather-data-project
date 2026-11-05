import json
from datetime import UTC, datetime
from pathlib import Path

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
    assert data["location"]["name"] == "Bucaramanga"
    assert data["location"]["utc_offset"] == "-5.0"
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


def _capture_url(monkeypatch):
    monkeypatch.setenv("WEATHERSTACK_API_KEY", "k")
    calls = {}

    def fake_get(url, **kwargs):
        calls["url"] = url
        return FakeResponse({"current": {}})

    monkeypatch.setattr(api_request.requests, "get", fake_get)
    return calls


def test_fetch_data_uses_https_by_default(monkeypatch):
    monkeypatch.delenv("WEATHERSTACK_API_URL", raising=False)
    calls = _capture_url(monkeypatch)
    api_request.fetch_data()
    assert calls["url"] == "https://api.weatherstack.com/current"


def test_fetch_data_url_override(monkeypatch):
    monkeypatch.setenv("WEATHERSTACK_API_URL", "http://api.weatherstack.com/current")
    calls = _capture_url(monkeypatch)
    api_request.fetch_data()
    assert calls["url"] == "http://api.weatherstack.com/current"


def test_fetch_data_explains_https_restricted(monkeypatch):
    monkeypatch.setenv("WEATHERSTACK_API_KEY", "k")
    payload = {"success": False, "error": {"code": 105, "type": "https_access_restricted"}}
    monkeypatch.setattr(api_request.requests, "get", lambda *a, **kw: FakeResponse(payload))
    with pytest.raises(RuntimeError, match="WEATHERSTACK_API_URL"):
        api_request.fetch_data()


def test_fetch_data_propagates_http_error(monkeypatch):
    monkeypatch.setenv("WEATHERSTACK_API_KEY", "k")
    monkeypatch.setattr(api_request.requests, "get", lambda *a, **kw: FakeResponse({}, 500))
    with pytest.raises(requests.exceptions.HTTPError):
        api_request.fetch_data()


NOW = datetime(2026, 11, 5, 12, 25, tzinfo=UTC)


def test_mock_fetch_data_is_bogota_stamped_and_deterministic():
    data = api_request.mock_fetch_data(now=NOW)
    assert data == api_request.mock_fetch_data(now=NOW)
    assert data["location"]["localtime"] == "2026-11-05 07:25"
    assert (
        data["location"]["localtime_epoch"] == 1793863500
    )  # local wall clock as UTC, like the API
    assert data["location"]["utc_offset"] == "-5.0"
    assert data["location"]["timezone_id"] == "America/Bogota"


def test_mock_fetch_data_city_and_no_shared_state():
    data = api_request.mock_fetch_data(city="Medellin", now=NOW)
    assert data["location"]["name"] == "Medellin"
    data["current"]["air_quality"]["co"] = "x"
    assert api_request.mock_fetch_data(now=NOW)["current"]["air_quality"]["co"] == "843"


def test_mock_matches_real_fixture():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "bucaramanga_current.json").read_text()
    )
    data = api_request.mock_fetch_data(now=NOW)
    assert data["current"] == fixture["current"]
    assert data["location"] == fixture["location"]


def test_get_cities(monkeypatch):
    monkeypatch.delenv("WEATHER_CITIES", raising=False)
    monkeypatch.delenv("WEATHER_CITY", raising=False)
    assert api_request.get_cities() == ["Bucaramanga"]
    monkeypatch.setenv("WEATHER_CITY", "Paris")
    assert api_request.get_cities() == ["Paris"]
    monkeypatch.setenv("WEATHER_CITIES", " Bogota , Cali,,")
    assert api_request.get_cities() == ["Bogota", "Cali"]
    monkeypatch.setenv("WEATHER_CITIES", " , ")
    assert api_request.get_cities() == ["Bucaramanga"]


def test_fetch_data_explicit_city(monkeypatch):
    monkeypatch.setenv("WEATHERSTACK_API_KEY", "k")
    calls = {}
    monkeypatch.setattr(
        api_request.requests,
        "get",
        lambda url, **kw: calls.update(kw) or FakeResponse({"current": {}}),
    )
    api_request.fetch_data("Cali")
    assert calls["params"]["query"] == "Cali"
