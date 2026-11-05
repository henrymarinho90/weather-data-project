"""Pure-function tests for docker/superset_setup.py (no Superset or network)."""

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "superset_setup", Path(__file__).resolve().parent.parent / "docker" / "superset_setup.py"
)
setup = importlib.util.module_from_spec(SPEC)
pytest.importorskip("requests")
SPEC.loader.exec_module(setup)

CONTRACT = {
    "weather_report": {
        "city", "observed_at_local", "observed_at_utc", "temperature", "feelslike",
        "humidity", "precip", "pressure", "cloudcover", "uv_index", "visibility",
        "wind_speed", "wind_dir", "weather_description", "is_day", "aq_pm2_5",
        "us_epa_index",
    },
    "daily_average": {
        "city", "date", "n_observations", "avg_temperature", "min_temperature",
        "max_temperature", "avg_wind_speed", "avg_humidity", "total_precip",
        "max_uv_index", "avg_pm2_5",
    },
    "air_quality_daily": {
        "city", "date", "n_observations", "avg_pm2_5", "avg_pm10", "avg_o3",
        "avg_no2", "avg_so2", "avg_co", "max_us_epa_index",
    },
    "astro_daily": {
        "city", "date", "sunrise", "sunset", "day_length_minutes", "moonrise",
        "moonset", "moon_phase", "moon_illumination",
    },
}  # fmt: skip

DATASETS = {table: i for i, table in enumerate(setup.TABLES, start=100)}
TABLE_BY_ID = {v: k for k, v in DATASETS.items()}


def referenced_columns(params):
    cols = set(params.get("all_columns", [])) | set(params.get("groupby", []))
    if "x_axis" in params:
        cols.add(params["x_axis"])
    for m in [*params.get("metrics", []), *([params["metric"]] if "metric" in params else [])]:
        if "column" in m:
            cols.add(m["column"]["column_name"])
        elif "sqlExpression" in m:
            cols.add("observed_at_utc")
            cols.add(m["sqlExpression"].split("(")[2].split(" ")[0])
    for item in params.get("order_by_cols", []):
        cols.add(json.loads(item)[0])
    return cols


def test_tables_match_contract():
    assert set(setup.TABLES) == set(CONTRACT)


def test_chart_names_unique_and_columns_in_contract():
    charts = setup.chart_definitions(DATASETS)
    names = [name for name, _, _ in charts]
    assert len(names) == len(set(names))
    for name, dataset_id, params in charts:
        assert params["viz_type"] == params["viz_type"].strip()
        missing = referenced_columns(params) - CONTRACT[TABLE_BY_ID[dataset_id]]
        assert not missing, f"{name}: {missing}"


def test_layout_is_consistent():
    charts = setup.chart_definitions(DATASETS)
    chart_ids = [(name, i) for i, (name, _, _) in enumerate(charts, start=1)]
    layout = setup.dashboard_layout(chart_ids)
    # every child id exists and parents chain is valid
    for key, node in layout.items():
        if key == "DASHBOARD_VERSION_KEY":
            continue
        for child in node.get("children", []):
            assert child in layout
            assert layout[child]["parents"][-1] == key or key == "ROOT_ID"
    seen = []
    for row_id in layout["GRID_ID"]["children"]:
        row = layout[row_id]
        assert sum(layout[c]["meta"]["width"] for c in row["children"]) <= 12
        seen += [layout[c]["meta"]["chartId"] for c in row["children"]]
    assert sorted(seen) == sorted(i for _, i in chart_ids)
    assert len(seen) == len(set(seen))


def test_every_chart_is_laid_out():
    laid_out = {name for row in setup.LAYOUT_ROWS for name, _ in row}
    assert laid_out == {name for name, _, _ in setup.chart_definitions(DATASETS)}


def test_city_filter_shape():
    f = setup.city_filter(1)
    json.dumps(f)
    assert f["filterType"] == "filter_select"
    assert f["targets"][0]["column"]["name"] == "city"
