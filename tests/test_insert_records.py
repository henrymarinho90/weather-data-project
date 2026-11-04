from api_request import mock_fetch_data
from insert_records import build_record


def test_build_record_maps_fields():
    data = mock_fetch_data()
    assert build_record(data) == (
        "New York",
        16,
        "Clear ",
        19,
        "2026-10-20 20:13",
        "-4.0",
    )


def test_build_record_uses_first_description_and_offset():
    data = mock_fetch_data()
    data["current"]["weather_descriptions"] = ["Rain", "Mist"]
    data["location"]["utc_offset"] = "5.5"
    record = build_record(data)
    assert record[2] == "Rain"
    assert record[5] == "5.5"
