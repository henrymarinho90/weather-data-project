import logging
import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import requests

API_URL = "https://api.weatherstack.com/current"
REQUEST_TIMEOUT = (5, 30)  # (connect, read) seconds

logger = logging.getLogger(__name__)


def fetch_data():
    api_key = os.environ.get("WEATHERSTACK_API_KEY")
    city = os.getenv("WEATHER_CITY", "New York")
    logger.info("Fetching data from the Weatherstack API...")
    if not api_key:
        raise RuntimeError("WEATHERSTACK_API_KEY environment variable is not set")
    try:
        response = requests.get(
            API_URL,
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
        raise RuntimeError(f"Weatherstack API error: {data.get('error')}")
    logger.info("API response received successfully.")
    return data


def mock_fetch_data(now=None):
    """Sample Weatherstack response stamped with the current New York time.

    The weather values are fixed, but each call is a new observation, so mock
    runs keep the pipeline (and its source freshness check) realistic without
    spending API calls. `now` (an aware datetime) makes it deterministic in tests.
    """
    local = (now or datetime.now(UTC)).astimezone(ZoneInfo("America/New_York"))
    offset_hours = local.utcoffset().total_seconds() / 3600
    return {
        "request": {
            "type": "City",
            "query": "New York, United States of America",
            "language": "en",
            "unit": "m",
        },
        "location": {
            "name": "New York",
            "country": "United States of America",
            "region": "New York",
            "lat": "40.714",
            "lon": "-74.006",
            "timezone_id": "America/New_York",
            "localtime": local.strftime("%Y-%m-%d %H:%M"),
            "localtime_epoch": int(local.timestamp()),
            "utc_offset": f"{offset_hours:.1f}",
        },
        "current": {
            "observation_time": "12:13 AM",
            "temperature": 16,
            "weather_code": 113,
            "weather_icons": [
                "https://cdn.worldweatheronline.com/images/wsymbols01_png_64/"
                "wsymbol_0008_clear_sky_night.png"
            ],
            "weather_descriptions": ["Clear "],
            "astro": {
                "sunrise": "07:13 AM",
                "sunset": "06:08 PM",
                "moonrise": "03:28 PM",
                "moonset": "01:02 AM",
                "moon_phase": "Waxing Gibbous",
                "moon_illumination": 63,
            },
            "air_quality": {
                "co": "198",
                "no2": "30.8",
                "o3": "41",
                "so2": "1.8",
                "pm2_5": "8.9",
                "pm10": "9.5",
                "us-epa-index": "1",
                "gb-defra-index": "1",
            },
            "wind_speed": 19,
            "wind_degree": 11,
            "wind_dir": "NNE",
            "pressure": 1024,
            "precip": 0,
            "humidity": 46,
            "cloudcover": 0,
            "feelslike": 11,
            "uv_index": 0,
            "visibility": 10,
            "is_day": "no",
        },
    }
