import logging
import os
import time

import psycopg2
from psycopg2.extras import Json

from api_request import fetch_data, get_cities, mock_fetch_data

DEFAULT_MONTHLY_CALL_LIMIT = 90
DEFAULT_CALL_INTERVAL_SECONDS = 5

logger = logging.getLogger(__name__)


def connect_to_db():
    logger.info("Connecting to the PostgreSQL database...")
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "db"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            dbname=os.getenv("DB_NAME"),
        )
    except psycopg2.Error:
        logger.exception("Could not connect to the database")
        raise


def create_table(conn):
    logger.info("Creating the raw_weather_data table if it doesn't exist...")
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE SCHEMA IF NOT EXISTS dev;
            CREATE TABLE IF NOT EXISTS dev.raw_weather_data (
                id SERIAL PRIMARY KEY,
                city TEXT,
                temperature FLOAT,
                weather_description TEXT,
                wind_speed FLOAT,
                time TIMESTAMP,
                inserted_at TIMESTAMP DEFAULT NOW(),
                utc_offset TEXT,
                payload JSONB,
                source TEXT
            );
            -- Existing tables predate these columns: idempotent migration
            ALTER TABLE dev.raw_weather_data ADD COLUMN IF NOT EXISTS payload JSONB;
            ALTER TABLE dev.raw_weather_data ADD COLUMN IF NOT EXISTS source TEXT;
        """)
    conn.commit()
    logger.info("Table is ready.")


def build_record(data):
    """Map a Weatherstack payload to the column tuple used by the INSERT."""
    weather = data["current"]
    location = data["location"]
    return (
        location["name"],
        weather["temperature"],
        weather["weather_descriptions"][0],
        weather["wind_speed"],
        location["localtime"],
        location["utc_offset"],
    )


def insert_records(conn, data, source="api"):
    logger.info("Inserting record into dev.raw_weather_data...")
    record = build_record(data)
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dev.raw_weather_data(
                city,
                temperature,
                weather_description,
                wind_speed,
                time,
                inserted_at,
                utc_offset,
                payload,
                source
            ) VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s, %s)
            """,
            (*record, Json(data), source),
        )
    conn.commit()
    logger.info("Record inserted.")


def api_calls_this_month(conn):
    """Real API calls recorded in the current UTC calendar month.

    Counts stored rows with source='api'. Failed calls insert nothing, so they
    are not counted (the monthly limit's headroom below the plan's 100 covers them).
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM dev.raw_weather_data
            WHERE source = 'api'
              AND inserted_at >= date_trunc('month', NOW() AT TIME ZONE 'UTC')
              AND inserted_at < date_trunc('month', NOW() AT TIME ZONE 'UTC') + INTERVAL '1 month'
            """
        )
        return cursor.fetchone()[0]


def ingest_city(conn, city, mock):
    """Fetch and store one city. Returns False when skipped by the budget guard."""
    if mock:
        insert_records(conn, mock_fetch_data(city=city), source="mock")
        return True
    limit = int(os.getenv("WEATHERSTACK_MONTHLY_CALL_LIMIT", DEFAULT_MONTHLY_CALL_LIMIT))
    used = api_calls_this_month(conn)
    if used >= limit:
        logger.warning("Monthly API budget reached (%s/%s calls): skipping %s", used, limit, city)
        return False
    insert_records(conn, fetch_data(city), source="api")
    return True


def ingest_cities(conn, cities, mock, sleep=time.sleep):
    """One API call per city, pausing between calls (free plan: 429 on back-to-back calls)."""
    interval = float(os.getenv("WEATHERSTACK_CALL_INTERVAL_SECONDS", DEFAULT_CALL_INTERVAL_SECONDS))
    for i, city in enumerate(cities):
        if i > 0 and not mock:
            sleep(interval)
        ingest_city(conn, city, mock)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = None
    try:
        mock = os.getenv("USE_MOCK_API", "true").lower() == "true"
        conn = connect_to_db()
        create_table(conn)
        ingest_cities(conn, get_cities(), mock)
    except Exception:
        logger.exception("Weather ingestion failed")
        raise
    finally:
        if conn is not None:
            conn.close()
            logger.info("Database connection closed.")
