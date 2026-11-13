from datetime import date

import pytest

from app.periods import PERIODS, period_range, previous_range, pct_change, periods_for_ui

TODAY = date(2026, 5, 20)  # a Wednesday


@pytest.mark.parametrize("key,expected", [
    ("today", (date(2026, 5, 20), date(2026, 5, 20))),
    ("yesterday", (date(2026, 5, 19), date(2026, 5, 19))),
    ("last_7_days", (date(2026, 5, 14), date(2026, 5, 20))),
    ("this_week", (date(2026, 5, 18), date(2026, 5, 24))),
    ("last_week", (date(2026, 5, 11), date(2026, 5, 17))),
    ("this_month", (date(2026, 5, 1), date(2026, 5, 31))),
    ("last_month", (date(2026, 4, 1), date(2026, 4, 30))),
    ("this_quarter", (date(2026, 4, 1), date(2026, 6, 30))),
    ("last_quarter", (date(2026, 1, 1), date(2026, 3, 31))),
    ("this_year", (date(2026, 1, 1), date(2026, 12, 31))),
    ("last_year", (date(2025, 1, 1), date(2025, 12, 31))),
    ("mtd", (date(2026, 5, 1), date(2026, 5, 20))),
    ("qtd", (date(2026, 4, 1), date(2026, 5, 20))),
    ("ytd", (date(2026, 1, 1), date(2026, 5, 20))),
])
def test_period_range(key, expected):
    assert period_range(key, TODAY) == expected


@pytest.mark.parametrize("key,expected", [
    ("today", (date(2026, 5, 19), date(2026, 5, 19))),
    ("last_7_days", (date(2026, 5, 7), date(2026, 5, 13))),
    ("this_week", (date(2026, 5, 11), date(2026, 5, 17))),
    ("last_month", (date(2026, 3, 1), date(2026, 3, 31))),
    ("this_quarter", (date(2026, 1, 1), date(2026, 3, 31))),
    ("last_year", (date(2024, 1, 1), date(2024, 12, 31))),
    ("mtd", (date(2026, 4, 1), date(2026, 4, 20))),
    ("ytd", (date(2025, 1, 1), date(2025, 5, 20))),
])
def test_previous_range(key, expected):
    assert previous_range(key, TODAY) == expected


def test_month_to_date_clipped_to_shorter_previous_month():
    assert previous_range("mtd", date(2026, 3, 31)) == (date(2026, 2, 1), date(2026, 2, 28))


def test_last_month_across_year_boundary():
    assert period_range("last_month", date(2026, 1, 15)) == (date(2025, 12, 1), date(2025, 12, 31))
    assert previous_range("last_month", date(2026, 1, 15)) == (date(2025, 11, 1), date(2025, 11, 30))


def test_previous_period_never_overlaps_current():
    for key in PERIODS:
        start, _ = period_range(key, TODAY)
        _, prev_end = previous_range(key, TODAY)
        assert prev_end < start, key


def test_pct_change():
    assert pct_change(110, 100) == pytest.approx(10.0)
    assert pct_change(50, 100) == pytest.approx(-50.0)
    assert pct_change(10, -20) == pytest.approx(150.0)
    assert pct_change(10, 0) is None
    assert pct_change(None, 5) is None


def test_periods_for_ui():
    ui = periods_for_ui(TODAY)
    assert len(ui) == len(PERIODS)
    assert ui[0] == {"key": "today", "label": "Today", "start": "2026-05-20", "end": "2026-05-20"}
