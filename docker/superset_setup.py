"""Register the weather database, datasets, charts and dashboard in Superset.

Safe to re-run: existing objects (matched by name) are reused, not duplicated.
Run inside the Superset container:
    docker exec superset_app python /app/docker/superset_setup.py
"""
import json
import os

import requests

BASE = "http://localhost:8088/api/v1"
ADMIN_USER = os.getenv("SUPERSET_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("SUPERSET_ADMIN_PASSWORD", "admin")
DB_NAME = "weather_db"
DB_URI = os.getenv("WEATHER_DB_URI", "postgresql://db_user:db_password@db:5432/db")
SCHEMA = "dev"
TABLES = ["weather_report", "daily_average", "stg_weather_data"]
DASHBOARD_TITLE = "Weather Dashboard"
REFRESH_SECONDS = 300


def login():
    session = requests.Session()
    token = session.post(f"{BASE}/security/login", json={
        "username": ADMIN_USER, "password": ADMIN_PASSWORD,
        "provider": "db", "refresh": True,
    }).json()["access_token"]
    session.headers["Authorization"] = f"Bearer {token}"
    csrf = session.get(f"{BASE}/security/csrf_token/").json()["result"]
    session.headers.update({"X-CSRFToken": csrf, "Referer": "http://localhost:8088"})
    return session


def find(session, resource, column, value):
    query = {"filters": [{"col": column, "opr": "eq", "value": value}]}
    result = session.get(f"{BASE}/{resource}/", params={"q": json.dumps(query)}).json()["result"]
    return result[0]["id"] if result else None


def create(session, resource, payload):
    response = session.post(f"{BASE}/{resource}/", json=payload)
    response.raise_for_status()
    return response.json()["id"]


def get_or_create(session, resource, column, value, payload):
    object_id = find(session, resource, column, value)
    if object_id:
        print(f"{resource} '{value}' already exists (id={object_id})")
        return object_id
    object_id = create(session, resource, payload)
    print(f"Created {resource} '{value}' (id={object_id})")
    return object_id


def metric(column, aggregate, label):
    return {"expressionType": "SIMPLE", "column": {"column_name": column},
            "aggregate": aggregate, "label": label}


def chart_definitions(datasets):
    return [
        ("Temperature and wind over time", datasets["weather_report"], {
            "viz_type": "echarts_timeseries_line",
            "x_axis": "weather_time_local",
            "time_grain_sqla": "PT1H",
            "metrics": [metric("temperature", "AVG", "Temperature (C)"),
                        metric("wind_speed", "AVG", "Wind speed (km/h)")],
            "groupby": [], "adhoc_filters": [], "row_limit": 10000,
            "markerEnabled": True,
        }),
        ("Daily average temperature", datasets["daily_average"], {
            "viz_type": "echarts_timeseries_bar",
            "x_axis": "date",
            "time_grain_sqla": "P1D",
            "metrics": [metric("avg_temperature", "MAX", "Avg temperature (C)")],
            "groupby": [], "adhoc_filters": [], "row_limit": 10000,
        }),
        ("Latest observations", datasets["weather_report"], {
            "viz_type": "table",
            "query_mode": "raw",
            "all_columns": ["weather_time_local", "city", "temperature",
                            "weather_description", "wind_speed"],
            "order_by_cols": [json.dumps(["weather_time_local", False])],
            "adhoc_filters": [], "row_limit": 50,
        }),
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
        layout[row] = {"type": "ROW", "id": row, "children": [chart],
                       "parents": ["ROOT_ID", "GRID_ID"],
                       "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        layout[chart] = {"type": "CHART", "id": chart, "children": [],
                         "parents": ["ROOT_ID", "GRID_ID", row],
                         "meta": {"chartId": chart_id, "width": 12, "height": 50,
                                  "sliceName": name}}
    return layout


def main():
    session = login()

    database_id = get_or_create(session, "database", "database_name", DB_NAME, {
        "database_name": DB_NAME, "sqlalchemy_uri": DB_URI, "expose_in_sqllab": True,
    })

    datasets = {}
    for table in TABLES:
        datasets[table] = get_or_create(session, "dataset", "table_name", table, {
            "database": database_id, "schema": SCHEMA, "table_name": table,
        })

    chart_ids = []
    for name, dataset_id, params in chart_definitions(datasets):
        chart_ids.append((name, get_or_create(session, "chart", "slice_name", name, {
            "slice_name": name, "viz_type": params["viz_type"],
            "datasource_id": dataset_id, "datasource_type": "table",
            "params": json.dumps({**params, "datasource": f"{dataset_id}__table"}),
        })))

    dashboard_id = get_or_create(session, "dashboard", "dashboard_title", DASHBOARD_TITLE, {
        "dashboard_title": DASHBOARD_TITLE, "slug": "weather", "published": True,
    })
    response = session.put(f"{BASE}/dashboard/{dashboard_id}", json={
        "position_json": json.dumps(dashboard_layout(chart_ids)),
        "json_metadata": json.dumps({"refresh_frequency": REFRESH_SECONDS}),
    })
    response.raise_for_status()
    for _, chart_id in chart_ids:
        session.put(f"{BASE}/chart/{chart_id}", json={"dashboards": [dashboard_id]}).raise_for_status()

    print(f"Dashboard ready: http://localhost:8089/superset/dashboard/weather/")


if __name__ == "__main__":
    main()
