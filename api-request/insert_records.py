import logging
import os

import psycopg2

from api_request import fetch_data, mock_fetch_data

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
                utc_offset TEXT
            );
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


def insert_records(conn, data):
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
                utc_offset
            ) VALUES (%s, %s, %s, %s, %s, NOW(), %s)
            """,
            record,
        )
    conn.commit()
    logger.info("Record inserted.")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = None
    try:
        if os.getenv("USE_MOCK_API", "true").lower() == "true":
            data = mock_fetch_data()
        else:
            data = fetch_data()
        conn = connect_to_db()
        create_table(conn)
        insert_records(conn, data)
    except Exception:
        logger.exception("Weather ingestion failed")
        raise
    finally:
        if conn is not None:
            conn.close()
            logger.info("Database connection closed.")
