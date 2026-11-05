import random
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import seed_test_data


def rows(days=10, seed=1):
    return list(seed_test_data.generate_rows(days, random.Random(seed)))


def test_two_rows_per_day():
    assert len(rows(10)) == 20


def test_deterministic_with_seed():
    assert rows(5, seed=7) == rows(5, seed=7)
    assert rows(5, seed=7) != rows(5, seed=8)


def test_utc_equals_local_minus_offset(monkeypatch):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 5)

    monkeypatch.setattr(seed_test_data, "date", FakeDate)
    result = rows(8)  # covers 2026-10-28 .. 2026-11-04
    offsets = set()
    for row in result:
        local, utc, offset = row[4], row[5], float(row[6])
        offsets.add(offset)
        assert utc == local - timedelta(hours=offset)
        expected = local.replace(tzinfo=ZoneInfo("America/Bogota")).astimezone(UTC)
        assert utc == expected.replace(tzinfo=None)
    assert offsets == {-5.0}  # Bogota has no DST
    assert all(isinstance(r[4], datetime) for r in result)
