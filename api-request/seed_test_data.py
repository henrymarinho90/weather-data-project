"""Populate dev.raw_weather_data with synthetic history for testing/dashboards.

Generates two observations per day (08:00 and 20:00 local time, matching the
DAG's twice-daily cadence) for the last N days, without calling the API.

Run inside the Airflow container:
    docker exec airflow_container python /opt/airflow/api-request/seed_test_data.py --days 30
"""
import argparse
import random
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from insert_records import connect_to_db, create_table

CITY = "New York"
TZ = ZoneInfo("America/New_York")
DESCRIPTIONS = ["Sunny", "Clear", "Partly cloudy", "Overcast", "Light rain", "Mist"]
WEIGHTS = [25, 20, 25, 15, 10, 5]


def generate_rows(days, rng):
    today = date.today()
    for d in range(days, 0, -1):
        day = today - timedelta(days=d)
        # Seasonal trend: roughly 0.25 C cooler per day going into autumn
        base = 12 + 0.25 * d
        for hour, diurnal in ((8, -3), (20, 1)):
            local = datetime.combine(day, time(hour), tzinfo=TZ)
            offset_hours = local.utcoffset().total_seconds() / 3600
            yield (
                CITY,
                round(base + diurnal + rng.gauss(0, 2.5)),
                rng.choices(DESCRIPTIONS, WEIGHTS)[0],
                rng.randint(5, 30),
                local.replace(tzinfo=None),
                local.astimezone(timezone.utc).replace(tzinfo=None),
                f"{offset_hours:.1f}",
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows = list(generate_rows(args.days, random.Random(args.seed)))
    conn = connect_to_db()
    try:
        create_table(conn)
        with conn.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO dev.raw_weather_data(
                    city, temperature, weather_description, wind_speed,
                    time, inserted_at, utc_offset
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, rows)
        conn.commit()
        print(f"Inserted {len(rows)} test rows for {CITY} ({args.days} days).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
