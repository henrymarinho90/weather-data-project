"""Register the weather database, datasets, charts and dashboard in Superset.

Safe to re-run without creating duplicates. Charts and the dashboard are
created from this file the first time; after that they belong to the Superset
UI, so visual edits (layout, colors, formats, titles) survive re-runs. Existing
objects only get renamed (RENAMED_CHARTS, LEGACY_DASHBOARD_TITLES) and the
connection string / dataset columns refreshed. SUPERSET_SETUP_RESET=true
overwrites every chart and the dashboard layout with the definitions below.
Run inside the Superset container:
    python /app/docker/superset_setup.py
    SUPERSET_SETUP_RESET=true python /app/docker/superset_setup.py
"""

import json
import os
import sys
from pathlib import Path

import requests

# Inside the superset container: localhost; the superset_setup service: http://superset:8088
SUPERSET_URL = os.getenv("SUPERSET_URL", "http://localhost:8088").rstrip("/")
BASE = f"{SUPERSET_URL}/api/v1"
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
DASHBOARD_TITLE = "Panel del clima"
DASHBOARD_SLUG = "weather"
# Older titles of the same dashboard, renamed to DASHBOARD_TITLE
LEGACY_DASHBOARD_TITLES = {"Weather Dashboard"}
RESET = os.getenv("SUPERSET_SETUP_RESET", "false").lower() == "true"

# Branding (docker/themes/): the theme is owned by the repo and updated on every run;
# it is attached to the dashboard (with CSS, palette and crest banner) only while the
# dashboard has no theme yet, or with SUPERSET_SETUP_RESET=true.
THEME_DIR = Path(__file__).resolve().parent / "themes"
THEME_NAME = "Atlético Bucaramanga"
THEME_FILE = THEME_DIR / "atletico_bucaramanga.json"
CSS_FILE = THEME_DIR / "atletico_bucaramanga.css"
COLOR_SCHEME = "atletico_bucaramanga"  # EXTRA_CATEGORICAL_COLOR_SCHEMES in superset_config.py
# Crest served by Directus (its host must be in DASHBOARD_IMAGE_DOMAINS); empty = no banner
LOGO_URL = os.getenv("DASHBOARD_LOGO_URL", "")
BANNER_ROW, BANNER_ID = "ROW-ab-banner", "MARKDOWN-ab-banner"
BANNER_HEIGHT = 18
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
            "Temperatura actual",
            report,
            big_number(latest_metric("temperature", "Temperatura (°C)"), "°C, última observación"),
        ),
        (
            "Humedad actual",
            report,
            big_number(latest_metric("humidity", "Humedad (%)"), "%, última observación"),
        ),
        (
            "PM2.5 actual",
            report,
            big_number(latest_metric("aq_pm2_5", "PM2.5 (µg/m³)"), "µg/m³, última observación"),
        ),
        (
            "Temperatura y viento",
            report,
            line_params(
                "observed_at_local",
                "PT1H",
                [
                    metric("temperature", "AVG", "Temperatura (°C)"),
                    metric("wind_speed", "AVG", "Viento (km/h)"),
                ],
            ),
        ),
        (
            "Humedad y sensación térmica",
            report,
            line_params(
                "observed_at_local",
                "PT1H",
                [
                    metric("humidity", "AVG", "Humedad (%)"),
                    metric("feelslike", "AVG", "Sensación térmica (°C)"),
                    metric("temperature", "AVG", "Temperatura (°C)"),
                ],
            ),
        ),
        (
            "Temperatura promedio diaria",
            daily,
            line_params(
                "date",
                "P1D",
                [metric("avg_temperature", "MAX", "Temperatura promedio (°C)")],
                bar=True,
            ),
        ),
        (
            "Lluvia diaria",
            daily,
            line_params("date", "P1D", [metric("total_precip", "MAX", "Lluvia (mm)")], bar=True),
        ),
        (
            "Índice UV",
            daily,
            line_params(
                "date", "P1D", [metric("max_uv_index", "MAX", "Índice UV máximo")], bar=True
            ),
        ),
        (
            "Calidad del aire (PM2.5 / PM10)",
            air,
            line_params(
                "date",
                "P1D",
                [
                    metric("avg_pm2_5", "MAX", "PM2.5 (µg/m³)"),
                    metric("avg_pm10", "MAX", "PM10 (µg/m³)"),
                ],
            ),
        ),
        (
            "Índice de calidad del aire (EPA)",
            air,
            line_params(
                "date",
                "P1D",
                [metric("max_us_epa_index", "MAX", "Índice de calidad del aire (EPA)")],
                bar=True,
            ),
        ),
        (
            "Resumen diario",
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
            "Sol y luna",
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


# English names of earlier versions -> current names (renamed in place, keeping edits)
RENAMED_CHARTS = {
    "Current temperature": "Temperatura actual",
    "Current humidity": "Humedad actual",
    "Current PM2.5": "PM2.5 actual",
    "Temperature and wind over time": "Temperatura y viento",
    "Humidity and feels-like": "Humedad y sensación térmica",
    "Daily average temperature": "Temperatura promedio diaria",
    "Daily precipitation": "Lluvia diaria",
    "UV index": "Índice UV",
    "Air quality (PM2.5 / PM10)": "Calidad del aire (PM2.5 / PM10)",
    "US EPA index": "Índice de calidad del aire (EPA)",
    "Daily summary": "Resumen diario",
    "Sun and moon": "Sol y luna",
}
BIG_NUMBERS = {"Temperatura actual", "Humedad actual", "PM2.5 actual"}

# Spanish labels for dataset columns (table headers, filter and axis names)
COLUMN_LABELS = {
    "city": "Ciudad",
    "date": "Fecha",
    "observed_at_local": "Hora local",
    "observed_at_utc": "Hora UTC",
    "temperature": "Temperatura (°C)",
    "feelslike": "Sensación térmica (°C)",
    "humidity": "Humedad (%)",
    "precip": "Lluvia (mm)",
    "pressure": "Presión (hPa)",
    "cloudcover": "Nubosidad (%)",
    "uv_index": "Índice UV",
    "visibility": "Visibilidad (km)",
    "wind_speed": "Viento (km/h)",
    "wind_dir": "Dirección del viento",
    "weather_description": "Descripción",
    "is_day": "Es de día",
    "aq_pm2_5": "PM2.5 (µg/m³)",
    "us_epa_index": "Índice EPA",
    "n_observations": "Observaciones",
    "avg_temperature": "Temp. promedio (°C)",
    "min_temperature": "Temp. mínima (°C)",
    "max_temperature": "Temp. máxima (°C)",
    "avg_wind_speed": "Viento promedio (km/h)",
    "avg_humidity": "Humedad promedio (%)",
    "total_precip": "Lluvia total (mm)",
    "max_uv_index": "Índice UV máximo",
    "avg_pm2_5": "PM2.5 promedio (µg/m³)",
    "avg_pm10": "PM10 promedio (µg/m³)",
    "avg_o3": "O3 promedio (µg/m³)",
    "avg_no2": "NO2 promedio (µg/m³)",
    "avg_so2": "SO2 promedio (µg/m³)",
    "avg_co": "CO promedio (µg/m³)",
    "max_us_epa_index": "Índice EPA máximo",
    "sunrise": "Amanecer",
    "sunset": "Atardecer",
    "day_length_minutes": "Duración del día (min)",
    "moonrise": "Salida de la luna",
    "moonset": "Puesta de la luna",
    "moon_phase": "Fase lunar",
    "moon_illumination": "Iluminación lunar (%)",
}
# Fields the dataset PUT accepts for a column (GET returns more)
COLUMN_FIELDS = (
    "id", "column_name", "type", "verbose_name", "description", "expression",
    "filterable", "groupby", "is_active", "is_dttm", "python_date_format", "extra",
)  # fmt: skip

# Dashboard rows, top to bottom: (chart name, width in the 12-column grid)
LAYOUT_ROWS = [
    [("Temperatura actual", 4), ("Humedad actual", 4), ("PM2.5 actual", 4)],
    [("Temperatura y viento", 6), ("Humedad y sensación térmica", 6)],
    [("Temperatura promedio diaria", 6), ("Lluvia diaria", 6)],
    [("Índice UV", 6), ("Calidad del aire (PM2.5 / PM10)", 6)],
    [("Índice de calidad del aire (EPA)", 12)],
    [("Resumen diario", 12)],
    [("Sol y luna", 12)],
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
            height = BIG_NUMBER_HEIGHT if name in BIG_NUMBERS else CHART_HEIGHT
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
        "name": "Ciudad",
        "filterType": "filter_select",
        "type": "NATIVE_FILTER",
        "targets": [{"datasetId": dataset_id, "column": {"name": "city"}}],
        # Preselect the home city so the "... actual" big numbers never mix in
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


def label_columns(session, dataset_id):
    """Set Spanish verbose names, keeping labels someone already set in the UI."""
    response = session.get(f"{BASE}/dataset/{dataset_id}", timeout=TIMEOUT)
    response.raise_for_status()
    columns, changed = [], False
    for column in response.json()["result"]["columns"]:
        label = COLUMN_LABELS.get(column["column_name"])
        if (
            label
            and (RESET or not column.get("verbose_name"))
            and column.get("verbose_name") != label
        ):
            column["verbose_name"] = label
            changed = True
        columns.append({k: column[k] for k in COLUMN_FIELDS if k in column})
    if not changed:
        return
    response = session.put(
        f"{BASE}/dataset/{dataset_id}", json={"columns": columns}, timeout=TIMEOUT
    )
    # Labels are cosmetic: a rejected update must not stop the charts and dashboard
    if not response.ok:
        print(
            f"Could not label columns of dataset {dataset_id}: "
            f"{response.status_code} {response.text[:300]}"
        )


def sync_chart(session, name, payload):
    """Create the chart, or rename/overwrite an existing one. Returns (id, created)."""
    chart_id = find(session, "chart", "slice_name", name)
    old = next((en for en, es in RENAMED_CHARTS.items() if es == name), None)
    if not chart_id and old and (chart_id := find(session, "chart", "slice_name", old)):
        print(f"Renaming chart '{old}' -> '{name}' (id={chart_id})")
        update = payload if RESET else {"slice_name": name}
    elif chart_id:
        update = payload if RESET else None
    else:
        response = session.post(f"{BASE}/chart/", json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        print(f"Created chart '{name}' (id={response.json()['id']})")
        return response.json()["id"], True
    if update:
        session.put(f"{BASE}/chart/{chart_id}", json=update, timeout=TIMEOUT).raise_for_status()
    return chart_id, False


def sync_dashboard(session):
    """Find the dashboard by slug (title may be edited in the UI). Returns (id, created)."""
    dashboard_id = find(session, "dashboard", "slug", DASHBOARD_SLUG)
    if not dashboard_id:
        response = session.post(
            f"{BASE}/dashboard/",
            json={"dashboard_title": DASHBOARD_TITLE, "slug": DASHBOARD_SLUG, "published": True},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        print(f"Created dashboard '{DASHBOARD_TITLE}'")
        return response.json()["id"], True
    response = session.get(f"{BASE}/dashboard/{dashboard_id}", timeout=TIMEOUT)
    response.raise_for_status()
    if RESET or response.json()["result"]["dashboard_title"] in LEGACY_DASHBOARD_TITLES:
        session.put(
            f"{BASE}/dashboard/{dashboard_id}",
            json={"dashboard_title": DASHBOARD_TITLE, "published": True},
            timeout=TIMEOUT,
        ).raise_for_status()
        print(f"Dashboard title set to '{DASHBOARD_TITLE}'")
    return dashboard_id, False


def sync_theme(session):
    """Create or update the repo theme by name. Returns its id."""
    payload = {"theme_name": THEME_NAME, "json_data": THEME_FILE.read_text()}
    # The theme API filters names with a custom text filter: match exactly here instead
    response = session.get(
        f"{BASE}/theme/",
        params={"q": json.dumps({"columns": ["id", "theme_name"], "page_size": 100})},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    theme_id = next(
        (t["id"] for t in response.json()["result"] if t["theme_name"] == THEME_NAME), None
    )
    if theme_id:
        session.put(f"{BASE}/theme/{theme_id}", json=payload, timeout=TIMEOUT).raise_for_status()
        print(f"Updated theme '{THEME_NAME}' (id={theme_id})")
        return theme_id
    response = session.post(f"{BASE}/theme/", json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    print(f"Created theme '{THEME_NAME}' (id={response.json()['id']})")
    return response.json()["id"]


def banner_markdown(logo_url):
    return (
        '<div class="ab-banner">'
        f'<img src="{logo_url}" alt="Escudo del Atlético Bucaramanga" height="72">'
        "<div><h1>Clima en Bucaramanga</h1>"
        "<p>La Ciudad Bonita, observada a las 7 a. m. y 7 p. m.</p></div>"
        "</div>"
    )


def add_banner(position, logo_url):
    """Put (or refresh) a full-width crest banner as the first row of the layout."""
    if BANNER_ID in position:
        position[BANNER_ID]["meta"]["code"] = banner_markdown(logo_url)
        return position
    grid = position.setdefault(
        "GRID_ID", {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]}
    )
    grid["children"].insert(0, BANNER_ROW)
    position[BANNER_ROW] = {
        "type": "ROW",
        "id": BANNER_ROW,
        "children": [BANNER_ID],
        "parents": ["ROOT_ID", "GRID_ID"],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
    }
    position[BANNER_ID] = {
        "type": "MARKDOWN",
        "id": BANNER_ID,
        "children": [],
        "parents": ["ROOT_ID", "GRID_ID", BANNER_ROW],
        "meta": {"width": 12, "height": BANNER_HEIGHT, "code": banner_markdown(logo_url)},
    }
    return position


def apply_branding(session, dashboard_id, theme_id, force):
    """Attach theme, CSS, palette and banner unless the dashboard already has a theme."""
    response = session.get(f"{BASE}/dashboard/{dashboard_id}", timeout=TIMEOUT)
    response.raise_for_status()
    dashboard = response.json()["result"]
    if dashboard.get("theme") and not force:
        print("Dashboard already has a theme: branding left as edited in the UI")
        return
    metadata = json.loads(dashboard.get("json_metadata") or "{}")
    metadata["color_scheme"] = COLOR_SCHEME
    position = json.loads(dashboard.get("position_json") or "{}")
    update = {
        "theme_id": theme_id,
        "css": CSS_FILE.read_text(),
        "json_metadata": json.dumps(metadata),
    }
    if LOGO_URL and position:
        update["position_json"] = json.dumps(add_banner(position, LOGO_URL))
    session.put(f"{BASE}/dashboard/{dashboard_id}", json=update, timeout=TIMEOUT).raise_for_status()
    print(f"Branding '{THEME_NAME}' applied to the dashboard")


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
        label_columns(session, dataset_id)
        datasets[table] = dataset_id

    chart_ids, new_charts = [], []
    for name, dataset_id, params in chart_definitions(datasets):
        payload = {
            "slice_name": name,
            "viz_type": params["viz_type"],
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "params": json.dumps({**params, "datasource": f"{dataset_id}__table"}),
        }
        chart_id, created = sync_chart(session, name, payload)
        chart_ids.append((name, chart_id))
        if created:
            new_charts.append(chart_id)

    dashboard_id, dashboard_created = sync_dashboard(session)
    if dashboard_created or RESET:
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
        print("Dashboard layout written")
        new_charts = [chart_id for _, chart_id in chart_ids]
    elif new_charts:
        print("New charts are not placed on the existing layout: drag them in from the UI")
    for chart_id in new_charts:
        session.put(
            f"{BASE}/chart/{chart_id}", json={"dashboards": [dashboard_id]}, timeout=TIMEOUT
        ).raise_for_status()
    apply_branding(session, dashboard_id, sync_theme(session), force=dashboard_created or RESET)

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
