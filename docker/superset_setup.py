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
TABLES = ["weather_report", "daily_average", "air_quality_daily", "astro_daily"]
# Staging is not a reporting interface; remove the dataset older versions created
RETIRED_DATASETS = ["stg_weather_data"]
DASHBOARD_TITLE = "Weather Dashboard"
# Preselected in the dashboard city filter
DEFAULT_CITY = os.environ.get("DASHBOARD_DEFAULT_CITY", "Bucaramanga")
REFRESH_SECONDS = 300


class LocalSession(requests.Session):
    """Session for http://localhost:8088 that keeps Superset's session cookie.

    Behind an HTTPS proxy (SUPERSET_PUBLIC_URL=https://...) Superset marks its
    session cookie Secure on every response, and requests never sends Secure
    cookies over plain http, so every POST/PUT would fail the CSRF check
    ("The CSRF session token is missing"). This script only ever talks to
    Superset inside its own container, so clearing the flag is safe.
    """

    def send(self, request, **kwargs):
        response = super().send(request, **kwargs)
        for cookie in self.cookies:
            cookie.secure = False
        return response


def login():
    session = LocalSession()
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


def latest_metric(column, label):
    """Value of `column` in the most recent observation (Postgres array_agg trick)."""
    return {
        "expressionType": "SQL",
        "sqlExpression": f"(array_agg({column} ORDER BY observed_at_utc DESC))[1]",
        "label": label,
    }


def line_params(x_axis, grain, metrics, groupby=("city",), bar=False):
    return {
        "viz_type": "echarts_timeseries_bar" if bar else "echarts_timeseries_line",
        "x_axis": x_axis,
        "time_grain_sqla": grain,
        "metrics": metrics,
        "groupby": list(groupby),
        "adhoc_filters": [],
        "row_limit": 10000,
        **({} if bar else {"markerEnabled": True}),
    }


def big_number(metric_def, subheader):
    return {
        "viz_type": "big_number_total",
        "metric": metric_def,
        "subheader": subheader,
        "adhoc_filters": [],
        "y_axis_format": "SMART_NUMBER",
        "time_format": "smart_date",
    }


def chart_definitions(datasets):
    report, daily = datasets["weather_report"], datasets["daily_average"]
    air, astro = datasets["air_quality_daily"], datasets["astro_daily"]
    # In the daily marts there is one row per city and day, so MAX just picks that value
    return [
        (
            "Current temperature",
            report,
            big_number(latest_metric("temperature", "Temperature (C)"), "C, latest observation"),
        ),
        (
            "Current humidity",
            report,
            big_number(latest_metric("humidity", "Humidity (%)"), "%, latest observation"),
        ),
        (
            "Current PM2.5",
            report,
            big_number(latest_metric("aq_pm2_5", "PM2.5 (ug/m3)"), "ug/m3, latest observation"),
        ),
        (
            "Temperature and wind over time",
            report,
            line_params(
                "observed_at_local",
                "PT1H",
                [
                    metric("temperature", "AVG", "Temperature (C)"),
                    metric("wind_speed", "AVG", "Wind speed (km/h)"),
                ],
            ),
        ),
        (
            "Humidity and feels-like",
            report,
            line_params(
                "observed_at_local",
                "PT1H",
                [
                    metric("humidity", "AVG", "Humidity (%)"),
                    metric("feelslike", "AVG", "Feels like (C)"),
                    metric("temperature", "AVG", "Temperature (C)"),
                ],
            ),
        ),
        (
            "Daily average temperature",
            daily,
            line_params(
                "date",
                "P1D",
                [metric("avg_temperature", "MAX", "Avg temperature (C)")],
                bar=True,
            ),
        ),
        (
            "Daily precipitation",
            daily,
            line_params(
                "date", "P1D", [metric("total_precip", "MAX", "Precipitation (mm)")], bar=True
            ),
        ),
        (
            "UV index",
            daily,
            line_params("date", "P1D", [metric("max_uv_index", "MAX", "Max UV index")], bar=True),
        ),
        (
            "Air quality (PM2.5 / PM10)",
            air,
            line_params(
                "date",
                "P1D",
                [
                    metric("avg_pm2_5", "MAX", "PM2.5 (ug/m3)"),
                    metric("avg_pm10", "MAX", "PM10 (ug/m3)"),
                ],
            ),
        ),
        (
            "US EPA index",
            air,
            line_params(
                "date", "P1D", [metric("max_us_epa_index", "MAX", "US EPA index")], bar=True
            ),
        ),
        (
            "Daily summary",
            daily,
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
        (
            "Sun and moon",
            astro,
            {
                "viz_type": "table",
                "query_mode": "raw",
                "all_columns": [
                    "date",
                    "city",
                    "sunrise",
                    "sunset",
                    "day_length_minutes",
                    "moon_phase",
                    "moon_illumination",
                ],
                "order_by_cols": [json.dumps(["date", False])],
                "adhoc_filters": [],
                "row_limit": 60,
            },
        ),
    ]


# Dashboard rows, top to bottom: (chart name, width in the 12-column grid)
LAYOUT_ROWS = [
    [("Current temperature", 4), ("Current humidity", 4), ("Current PM2.5", 4)],
    [("Temperature and wind over time", 6), ("Humidity and feels-like", 6)],
    [("Daily average temperature", 6), ("Daily precipitation", 6)],
    [("UV index", 6), ("Air quality (PM2.5 / PM10)", 6)],
    [("US EPA index", 12)],
    [("Daily summary", 12)],
    [("Sun and moon", 12)],
]
BIG_NUMBER_HEIGHT = 20
CHART_HEIGHT = 50


def dashboard_layout(chart_ids, rows=None):
    """Build position_json; `chart_ids` is [(name, id)], `rows` a list of [(name, width)]."""
    ids = dict(chart_ids)
    rows = LAYOUT_ROWS if rows is None else rows
    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
        "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": DASHBOARD_TITLE}},
    }
    n = 0
    for r, row_items in enumerate(rows, start=1):
        row = f"ROW-{r}"
        layout["GRID_ID"]["children"].append(row)
        layout[row] = {
            "type": "ROW",
            "id": row,
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        for name, width in row_items:
            if name not in ids:
                continue
            n += 1
            chart = f"CHART-{n}"
            layout[row]["children"].append(chart)
            height = BIG_NUMBER_HEIGHT if name.startswith("Current ") else CHART_HEIGHT
            layout[chart] = {
                "type": "CHART",
                "id": chart,
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", row],
                "meta": {
                    "chartId": ids[name],
                    "width": width,
                    "height": height,
                    "sliceName": name,
                },
            }
    return layout


def city_filter(dataset_id):
    """Native dashboard filter on `city`, applied to every chart that has that column."""
    return {
        "id": "NATIVE_FILTER-city",
        "name": "City",
        "filterType": "filter_select",
        "type": "NATIVE_FILTER",
        "targets": [{"datasetId": dataset_id, "column": {"name": "city"}}],
        # Preselect the home city so the "Current ..." big numbers never mix in
        # older rows of other cities (e.g. the New York history)
        "defaultDataMask": {
            "extraFormData": {"filters": [{"col": "city", "op": "IN", "val": [DEFAULT_CITY]}]},
            "filterState": {"value": [DEFAULT_CITY]},
            "ownState": {},
        },
        "controlValues": {
            "multiSelect": True,
            "enableEmptyFilter": False,
            "defaultToFirstItem": False,
            "inverseSelection": False,
            "searchAllOptions": False,
        },
        "cascadeParentIds": [],
        "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
    }


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
            "json_metadata": json.dumps(
                {
                    "refresh_frequency": REFRESH_SECONDS,
                    "native_filter_configuration": [city_filter(datasets["weather_report"])],
                }
            ),
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

    public_url = os.getenv("SUPERSET_PUBLIC_URL", "http://localhost:8089").rstrip("/")
    print(f"Dashboard ready: {public_url}/superset/dashboard/weather/")


if __name__ == "__main__":
    main()
