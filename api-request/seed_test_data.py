"""Populate dev.raw_weather_data with synthetic history for testing/dashboards.

Generates two observations per day for the last N days, without calling the API.
Observations are at 07:00 and 19:00 Bogota local time, matching the DAG's schedule
(00:00 and 12:00 UTC). Rows have no payload/source (like pre-migration rows).
Re-running is idempotent: rows whose (city, time) already exist are skipped.

Run inside the Airflow container:
    docker exec airflow_container python /opt/airflow/api-request/seed_test_data.py --days 30
"""

import argparse
import random
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from insert_records import connect_to_db, create_table

CITY = "Bucaramanga"
TZ = ZoneInfo("America/Bogota")
DESCRIPTIONS = ["Sunny", "Clear", "Partly cloudy", "Overcast", "Light rain", "Mist"]
WEIGHTS = [25, 20, 25, 15, 10, 5]

INSERT_IF_MISSING = """
    INSERT INTO dev.raw_weather_data(
        city, temperature, weather_description, wind_speed,
        time, inserted_at, utc_offset
    )
    SELECT %s, %s, %s, %s, %s, %s, %s
    WHERE NOT EXISTS (
        SELECT 1 FROM dev.raw_weather_data WHERE city = %s AND time = %s
    )
"""


def generate_rows(days, rng):
    today = date.today()
    for d in range(days, 0, -1):
        day = today - timedelta(days=d)
        # Seasonal trend: roughly 0.25 C cooler per day going into autumn
        base = 12 + 0.25 * d
        for hour, diurnal in ((7, -3), (19, 1)):
            local = datetime.combine(day, time(hour), tzinfo=TZ)
            offset_hours = local.utcoffset().total_seconds() / 3600
            yield (
                CITY,
                round(base + diurnal + rng.gauss(0, 2.5)),
                rng.choices(DESCRIPTIONS, WEIGHTS)[0],
                rng.randint(5, 30),
                local.replace(tzinfo=None),
                local.astimezone(UTC).replace(tzinfo=None),
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
        inserted = 0
        with conn.cursor() as cursor:
            for row in rows:
                cursor.execute(INSERT_IF_MISSING, (*row, row[0], row[4]))
                inserted += cursor.rowcount
        conn.commit()
        print(
            f"Inserted {inserted} new test rows for {CITY} "
            f"({len(rows) - inserted} already existed, {args.days} days)."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
