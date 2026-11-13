"""Date period shortcuts and their previous-period equivalents.

All ranges are inclusive (start, end) date pairs.
"""
from calendar import monthrange
from datetime import date, timedelta

# key -> (label, kind, argument)
PERIODS = {
    "today": ("Today", "unit", ("day", 0)),
    "yesterday": ("Yesterday", "unit", ("day", -1)),
    "last_7_days": ("Last 7 days", "rolling", 7),
    "last_30_days": ("Last 30 days", "rolling", 30),
    "last_90_days": ("Last 90 days", "rolling", 90),
    "this_week": ("This week", "unit", ("week", 0)),
    "last_week": ("Last week", "unit", ("week", -1)),
    "this_month": ("This month", "unit", ("month", 0)),
    "last_month": ("Last month", "unit", ("month", -1)),
    "this_quarter": ("This quarter", "unit", ("quarter", 0)),
    "last_quarter": ("Last quarter", "unit", ("quarter", -1)),
    "this_year": ("This year", "unit", ("year", 0)),
    "last_year": ("Last year", "unit", ("year", -1)),
    "mtd": ("Month to date", "todate", "month"),
    "qtd": ("Quarter to date", "todate", "quarter"),
    "ytd": ("Year to date", "todate", "year"),
}


def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def unit_range(unit, d, offset=0):
    """The calendar unit containing d, shifted by offset units."""
    if unit == "day":
        start = d + timedelta(days=offset)
        return start, start
    if unit == "week":
        start = d - timedelta(days=d.weekday()) + timedelta(weeks=offset)
        return start, start + timedelta(days=6)
    months = {"month": 1, "quarter": 3, "year": 12}[unit]
    if unit == "month":
        base = d.replace(day=1)
    elif unit == "quarter":
        base = date(d.year, (d.month - 1) // 3 * 3 + 1, 1)
    else:
        base = date(d.year, 1, 1)
    start = _add_months(base, offset * months)
    return start, _add_months(start, months) - timedelta(days=1)


def period_range(key, today=None):
    today = today or date.today()
    _, kind, arg = PERIODS[key]
    if kind == "unit":
        unit, offset = arg
        return unit_range(unit, today, offset)
    if kind == "rolling":
        return today - timedelta(days=arg - 1), today
    start, _ = unit_range(arg, today)
    return start, today


def previous_range(key, today=None):
    today = today or date.today()
    _, kind, arg = PERIODS[key]
    if kind == "unit":
        unit, offset = arg
        return unit_range(unit, today, offset - 1)
    if kind == "rolling":
        start, _ = period_range(key, today)
        return start - timedelta(days=arg), start - timedelta(days=1)
    cur_start, _ = unit_range(arg, today)
    prev_start, prev_end = unit_range(arg, today, -1)
    return prev_start, min(prev_start + (today - cur_start), prev_end)


def periods_for_ui(today=None):
    today = today or date.today()
    result = []
    for key, (label, _, _) in PERIODS.items():
        start, end = period_range(key, today)
        result.append({"key": key, "label": label, "start": start.isoformat(), "end": end.isoformat()})
    return result


def pct_change(current, previous):
    if previous in (None, 0) or current is None:
        return None
    return (float(current) - float(previous)) / abs(float(previous)) * 100.0
