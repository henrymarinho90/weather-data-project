import os
import requests

api_key = os.environ.get("WEATHERSTACK_API_KEY")
city = os.getenv("WEATHER_CITY", "New York")
api_url = "https://api.weatherstack.com/current"

def fetch_data():
    print("Fetching data from the Weatherstack API...")
    try:
        if not api_key:
            raise RuntimeError("WEATHERSTACK_API_KEY environment variable is not set")
        response = requests.get(api_url, params={"access_key": api_key, "query": city})
        response.raise_for_status()
        data = response.json()
        # Weatherstack reports errors (bad key, quota exceeded) with HTTP 200
        if data.get("success") is False:
            raise RuntimeError(f"Weatherstack API error: {data.get('error')}")
        print("API Response received succesfully.")
        return data
    except requests.exceptions.RequestException as e:
        print(f"An error occurred:{e}")
        raise
    
def mock_fetch_data():
    return {'request': {'type': 'City', 'query': 'New York, United States of America', 'language': 'en', 'unit': 'm'}, 'location': {'name': 'New York', 'country': 'United States of America', 'region': 'New York', 'lat': '40.714', 'lon': '-74.006', 'timezone_id': 'America/New_York', 'localtime': '2026-10-20 20:13', 'localtime_epoch': 1792527180, 'utc_offset': '-4.0'}, 'current': {'observation_time': '12:13 AM', 'temperature': 16, 'weather_code': 113, 'weather_icons': ['https://cdn.worldweatheronline.com/images/wsymbols01_png_64/wsymbol_0008_clear_sky_night.png'], 'weather_descriptions': ['Clear '], 'astro': {'sunrise': '07:13 AM', 'sunset': '06:08 PM', 'moonrise': '03:28 PM', 'moonset': '01:02 AM', 'moon_phase': 'Waxing Gibbous', 'moon_illumination': 63}, 'air_quality': {'co': '198', 'no2': '30.8', 'o3': '41', 'so2': '1.8', 'pm2_5': '8.9', 'pm10': '9.5', 'us-epa-index': '1', 'gb-defra-index': '1'}, 'wind_speed': 19, 'wind_degree': 11, 'wind_dir': 'NNE', 'pressure': 1024, 'precip': 0, 'humidity': 46, 'cloudcover': 0, 'feelslike': 11, 'uv_index': 0, 'visibility': 10, 'is_day': 'no'}}
