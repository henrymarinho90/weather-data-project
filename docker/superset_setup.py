"""Register the weather database, datasets, charts and dashboard in Superset.

Safe to re-run: objects are matched by name and updated in place (connection
string, chart definitions, dashboard layout), so changes in .env or in the dbt
models are applied without creating duplicates.
Run inside the Superset container:
    docker exec superset_app python /app/docker/superset_setup.py
"""

import json
import os
import sys

import requests

BASE = "http://localhost:8088/api/v1"
TIMEOUT = 30
ADMIN_USER = os.getenv("SUPERSET_ADMIN_USER", "admin")
# docker-init.sh creates the admin with $ADMIN_PASSWORD (SUPERSET_ADMIN_PASSWORD in .env)
ADMIN_PASSWORD = os.getenv("SUPERSET_ADMIN_PASSWORD", os.getenv("ADMIN_PASSWORD", "admin"))
DB_NAME = "weather_db"
# Set by docker-compose from .env: the read-only weather_reader role
DB_URI = os.getenv("WEATHER_DB_URI")
SCHEMA = "dev"
TABLES = ["weather_report", "daily_average"]
# Staging is not a reporting interface; remove the dataset older versions created
RETIRED_DATASETS = ["stg_weather_data"]
DASHBOARD_TITLE = "Weather Dashboard"
REFRESH_SECONDS = 300


def login():
    session = requests.Session()
    response = session.post(
        f"{BASE}/security/login",
        json={
            "username": ADMIN_USER,
            "password": ADMIN_PASSWORD,
            "provider": "db",
            "refresh": True,
        },
        timeout=TIMEOUT,
    )
    if response.status_code == 401:
        sys.exit(
            f"Login as '{ADMIN_USER}' failed. If you changed the admin password in the UI, "
            "pass it with: docker exec -e SUPERSET_ADMIN_PASSWORD=... superset_app python "
            "/app/docker/superset_setup.py"
        )
    response.raise_for_status()
    session.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    csrf = session.get(f"{BASE}/security/csrf_token/", timeout=TIMEOUT)
    csrf.raise_for_status()
    session.headers.update(
        {"X-CSRFToken": csrf.json()["result"], "Referer": "http://localhost:8088"}
    )
    return session


def find(session, resource, column, value):
    query = {"filters": [{"col": column, "opr": "eq", "value": value}]}
    response = session.get(f"{BASE}/{resource}/", params={"q": json.dumps(query)}, timeout=TIMEOUT)
    response.raise_for_status()
    result = response.json()["result"]
    return result[0]["id"] if result else None


def upsert(session, resource, column, value, payload, update=None):
    """Create the object, or update an existing one with `update` (default: payload)."""
    object_id = find(session, resource, column, value)
    if object_id:
        response = session.put(
            f"{BASE}/{resource}/{object_id}", json=update or payload, timeout=TIMEOUT
        )
        response.raise_for_status()
        print(f"Updated {resource} '{value}' (id={object_id})")
        return object_id
    response = session.post(f"{BASE}/{resource}/", json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    object_id = response.json()["id"]
    print(f"Created {resource} '{value}' (id={object_id})")
    return object_id


def metric(column, aggregate, label):
    return {
        "expressionType": "SIMPLE",
        "column": {"column_name": column},
        "aggregate": aggregate,
        "label": label,
    }


def chart_definitions(datasets):
    return [
        (
            "Temperature and wind over time",
            datasets["weather_report"],
            {
                "viz_type": "echarts_timeseries_line",
                "x_axis": "observed_at_local",
                "time_grain_sqla": "PT1H",
                "metrics": [
                    metric("temperature", "AVG", "Temperature (C)"),
                    metric("wind_speed", "AVG", "Wind speed (km/h)"),
                ],
                "groupby": ["city"],
                "adhoc_filters": [],
                "row_limit": 10000,
                "markerEnabled": True,
            },
        ),
        (
            "Daily average temperature",
            datasets["daily_average"],
            {
                "viz_type": "echarts_timeseries_bar",
                "x_axis": "date",
                "time_grain_sqla": "P1D",
                # One row per city and day, so MAX just picks that row's value
                "metrics": [metric("avg_temperature", "MAX", "Avg temperature (C)")],
                "groupby": ["city"],
                "adhoc_filters": [],
                "row_limit": 10000,
            },
        ),
        (
            "Daily summary",
            datasets["daily_average"],
            {
                "viz_type": "table",
                "query_mode": "raw",
                # n_observations shows how many samples each daily average is based on
                "all_columns": [
                    "date",
                    "city",
                    "n_observations",
                    "avg_temperature",
                    "min_temperature",
                    "max_temperature",
                    "avg_wind_speed",
                ],
                "order_by_cols": [json.dumps(["date", False])],
                "adhoc_filters": [],
                "row_limit": 60,
            },
        ),
    ]


def dashboard_layout(chart_ids):
    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
        "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": DASHBOARD_TITLE}},
    }
    # One full-width chart per row
    for i, (name, chart_id) in enumerate(chart_ids, start=1):
        row, chart = f"ROW-{i}", f"CHART-{i}"
        layout["GRID_ID"]["children"].append(row)
        layout[row] = {
            "type": "ROW",
            "id": row,
            "children": [chart],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        layout[chart] = {
            "type": "CHART",
            "id": chart,
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row],
            "meta": {"chartId": chart_id, "width": 12, "height": 50, "sliceName": name},
        }
    return layout


def main():
    if not DB_URI:
        sys.exit("WEATHER_DB_URI is not set (docker-compose sets it from .env)")
    session = login()

    database_id = upsert(
        session,
        "database",
        "database_name",
        DB_NAME,
        {"database_name": DB_NAME, "sqlalchemy_uri": DB_URI, "expose_in_sqllab": True},
        update={"sqlalchemy_uri": DB_URI, "expose_in_sqllab": True},
    )

    datasets = {}
    for table in TABLES:
        dataset_id = find(session, "dataset", "table_name", table)
        if not dataset_id:
            dataset_id = upsert(
                session,
                "dataset",
                "table_name",
                table,
                {"database": database_id, "schema": SCHEMA, "table_name": table},
            )
        # Pick up column changes from the dbt models
        session.put(f"{BASE}/dataset/{dataset_id}/refresh", timeout=TIMEOUT).raise_for_status()
        datasets[table] = dataset_id

    chart_ids = []
    for name, dataset_id, params in chart_definitions(datasets):
        payload = {
            "slice_name": name,
            "viz_type": params["viz_type"],
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "params": json.dumps({**params, "datasource": f"{dataset_id}__table"}),
        }
        chart_ids.append((name, upsert(session, "chart", "slice_name", name, payload)))

    dashboard_id = upsert(
        session,
        "dashboard",
        "dashboard_title",
        DASHBOARD_TITLE,
        {"dashboard_title": DASHBOARD_TITLE, "slug": "weather", "published": True},
        update={"published": True},
    )
    session.put(
        f"{BASE}/dashboard/{dashboard_id}",
        json={
            "position_json": json.dumps(dashboard_layout(chart_ids)),
            "json_metadata": json.dumps({"refresh_frequency": REFRESH_SECONDS}),
        },
        timeout=TIMEOUT,
    ).raise_for_status()
    for _, chart_id in chart_ids:
        session.put(
            f"{BASE}/chart/{chart_id}", json={"dashboards": [dashboard_id]}, timeout=TIMEOUT
        ).raise_for_status()

    # Charts from older versions of this script that are no longer defined
    current = {name for name, _ in chart_ids}
    for old in ("Latest observations",):
        if old not in current and (chart_id := find(session, "chart", "slice_name", old)):
            session.delete(f"{BASE}/chart/{chart_id}", timeout=TIMEOUT).raise_for_status()
            print(f"Deleted retired chart '{old}'")
    for table in RETIRED_DATASETS:
        if dataset_id := find(session, "dataset", "table_name", table):
            session.delete(f"{BASE}/dataset/{dataset_id}", timeout=TIMEOUT).raise_for_status()
            print(f"Deleted retired dataset '{table}'")

    print("Dashboard ready: http://localhost:8089/superset/dashboard/weather/")


if __name__ == "__main__":
    main()
