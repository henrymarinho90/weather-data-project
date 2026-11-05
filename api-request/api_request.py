import copy
import logging
import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import requests

# HTTPS by default. Weatherstack's free plan may reject HTTPS (error 105,
# https_access_restricted); set WEATHERSTACK_API_URL to the http:// URL only if
# you accept the API key travelling unencrypted
DEFAULT_API_URL = "https://api.weatherstack.com/current"
REQUEST_TIMEOUT = (5, 30)  # (connect, read) seconds

DEFAULT_CITY = "Bucaramanga"
BOGOTA_TZ = ZoneInfo("America/Bogota")

logger = logging.getLogger(__name__)


def get_cities():
    """Cities to fetch: WEATHER_CITIES (comma-separated), else WEATHER_CITY, else Bucaramanga."""
    raw = os.getenv("WEATHER_CITIES") or os.getenv("WEATHER_CITY") or DEFAULT_CITY
    return [c.strip() for c in raw.split(",") if c.strip()] or [DEFAULT_CITY]


def fetch_data(city=None):
    api_key = os.environ.get("WEATHERSTACK_API_KEY")
    city = city or get_cities()[0]
    logger.info("Fetching data from the Weatherstack API...")
    if not api_key:
        raise RuntimeError("WEATHERSTACK_API_KEY environment variable is not set")
    try:
        response = requests.get(
            os.getenv("WEATHERSTACK_API_URL") or DEFAULT_API_URL,
            params={"access_key": api_key, "query": city},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        logger.exception("Weatherstack request failed")
        raise
    data = response.json()
    # Weatherstack reports errors (bad key, quota exceeded) with HTTP 200
    if data.get("success") is False:
        error = data.get("error")
        hint = ""
        if isinstance(error, dict) and error.get("code") == 105:
            hint = " (plan does not allow HTTPS: upgrade, or set WEATHERSTACK_API_URL to http://)"
        raise RuntimeError(f"Weatherstack API error: {error}{hint}")
    logger.info("API response received successfully.")
    return data


# Real Bucaramanga /current response (free plan); localtime fields are re-stamped per call
_MOCK_RESPONSE = {
    "request": {
        "type": "City",
        "query": "Bucaramanga, Colombia",
        "language": "en",
        "unit": "m",
    },
    "location": {
        "name": "Bucaramanga",
        "country": "Colombia",
        "region": "Santander",
        "lat": "7.130",
        "lon": "-73.126",
        "timezone_id": "America/Bogota",
        "localtime": "2026-11-05 07:25",
        "localtime_epoch": 1793863500,
        "utc_offset": "-5.0",
    },
    "current": {
        "observation_time": "12:25 PM",
        "temperature": 19,
        "weather_code": 353,
        "weather_icons": [
            "https://cdn.worldweatheronline.com/images/wsymbols01_png_64/"
            "wsymbol_0009_light_rain_showers.png"
        ],
        "weather_descriptions": ["Light rain shower"],
        "astro": {
            "sunrise": "05:41 AM",
            "sunset": "05:32 PM",
            "moonrise": "02:37 AM",
            "moonset": "02:56 PM",
            "moon_phase": "Waning Crescent",
            "moon_illumination": 18,
        },
        "air_quality": {
            "co": "843",
            "no2": "15.7",
            "o3": "48",
            "so2": "2.7",
            "pm2_5": "7",
            "pm10": "7.2",
            "us-epa-index": "1",
            "gb-defra-index": "1",
        },
        "wind_speed": 4,
        "wind_degree": 116,
        "wind_dir": "ESE",
        "pressure": 1014,
        "precip": 0.2,
        "humidity": 88,
        "cloudcover": 58,
        "feelslike": 20,
        "uv_index": 0,
        "visibility": 10,
        "is_day": "yes",
    },
}


def mock_fetch_data(city=None, now=None):
    """Sample Weatherstack response for `city`, stamped with the current Bogota time.

    The weather values are fixed, but each call is a new observation, so mock
    runs keep the pipeline (and its source freshness check) realistic without
    spending API calls. `now` (an aware datetime) makes it deterministic in tests.
    """
    data = copy.deepcopy(_MOCK_RESPONSE)
    local = (now or datetime.now(UTC)).astimezone(BOGOTA_TZ)
    data["location"].update(
        name=city or DEFAULT_CITY,
        timezone_id="America/Bogota",
        localtime=local.strftime("%Y-%m-%d %H:%M"),
        # Like the real API, the epoch is the local wall clock read as UTC
        localtime_epoch=int(local.replace(tzinfo=UTC).timestamp()),
        utc_offset="-5.0",
    )
    data["current"]["observation_time"] = (now or datetime.now(UTC)).strftime("%I:%M %p")
    return data
