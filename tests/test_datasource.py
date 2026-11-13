from datetime import date

import pytest

from app.datasource import DataSource, classify_columns, shape_chart, BLANK_LABEL, OTHER_LABEL

COLUMNS = ["date_sale", "date_shipped", "region", "channel", "euro_revenue", "ms_units"]


def render(composed):
    """Render a psycopg2 Composed without a database connection."""
    from psycopg2 import sql

    def walk(c):
        if isinstance(c, sql.Composed):
            return "".join(walk(x) for x in c.seq)
        if isinstance(c, sql.SQL):
            return c.string
        if isinstance(c, sql.Identifier):
            return ".".join('"%s"' % s.replace('"', '""') for s in c.strings)
        if isinstance(c, sql.Literal):
            return repr(c.wrapped)
        raise TypeError(c)
    return walk(composed)


@pytest.fixture
def ds():
    return DataSource("demo", "sales_demo", COLUMNS, "Sales")


def test_classify_columns():
    cols = classify_columns(COLUMNS)
    assert cols["euro"] == ["euro_revenue"]
    assert cols["measures"] == ["ms_units"]
    assert cols["date"] == "date_sale"
    assert cols["dates"] == ["date_sale", "date_shipped"]
    assert cols["attributes"] == ["region", "channel"]


def test_where_parameterises_values(ds):
    where, params = ds.build_where({"region": ["North", BLANK_LABEL]}, date(2026, 1, 1), date(2026, 1, 31))
    text = render(where)
    assert '"region"::text = ANY(%s)' in text
    assert '"region" IS NULL' in text
    assert '"date_sale" >= %s' in text and '"date_sale" < %s' in text
    assert params == [["North"], date(2026, 1, 1), date(2026, 2, 1)]
    assert "North" not in text


def test_empty_where(ds):
    where, params = ds.build_where({}, None, None)
    assert render(where) == "" and params == []


@pytest.mark.parametrize("bad", ['region"; DROP TABLE x; --', "euro_revenue", "unknown"])
def test_unknown_filter_column_rejected(ds, bad):
    with pytest.raises(ValueError):
        ds.build_where({bad: ["x"]})


def test_unknown_measure_rejected(ds):
    where, _ = ds.build_where()
    with pytest.raises(ValueError):
        ds.build_kpi_query("region", where)


def test_kpi_query(ds):
    where, _ = ds.build_where()
    assert render(ds.build_kpi_query("euro_revenue", where)) == \
        'SELECT SUM("euro_revenue") AS value FROM "demo"."sales_demo"'


def test_chart_query_with_date_grain_and_breakdown(ds):
    where, _ = ds.build_where()
    text = render(ds.build_chart_query("date_sale", ["ms_units"], where, breakdown="region", grain="month"))
    assert "date_trunc('month', \"date_sale\")::date AS label" in text
    assert '"region" AS series' in text
    assert 'SUM("ms_units") AS "ms_units"' in text
    assert "GROUP BY 1, 2" in text


def test_chart_query_multiple_measures(ds):
    where, _ = ds.build_where()
    text = render(ds.build_chart_query("region", ["euro_revenue", "ms_units"], where))
    assert text == ('SELECT "region" AS label, SUM("euro_revenue") AS "euro_revenue", '
                    'SUM("ms_units") AS "ms_units" FROM "demo"."sales_demo" GROUP BY 1 ORDER BY 1')


def test_chart_query_needs_a_valid_measure(ds):
    where, _ = ds.build_where()
    with pytest.raises(ValueError):
        ds.build_chart_query("region", [], where)
    with pytest.raises(ValueError):
        ds.build_chart_query("region", ["ms_units", "region"], where)


def test_chart_query_rejects_bad_grain(ds):
    where, _ = ds.build_where()
    with pytest.raises(ValueError):
        ds.build_chart_query("date_sale", ["ms_units"], where, grain="decade")


def test_table_query(ds):
    where, _ = ds.build_where()
    text = render(ds.build_table_query(["region"], ["euro_revenue", "ms_units"], where, 100))
    assert text == ('SELECT "region", SUM("euro_revenue") AS "euro_revenue", SUM("ms_units") AS "ms_units" '
                    'FROM "demo"."sales_demo" GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT 100')


def test_shape_chart_simple_sorted_by_value():
    rows = [{"label": "A", "m": 1}, {"label": "B", "m": 5}, {"label": None, "m": 2}]
    out = shape_chart(rows, ["m"], False, False, 10)
    assert out["labels"] == ["B", BLANK_LABEL, "A"]
    assert out["datasets"] == [{"measure": "m", "series": None, "data": [5, 2, 1]}]


def test_shape_chart_multiple_measures_sorted_by_first():
    rows = [{"label": "A", "m1": 1, "m2": 90}, {"label": "B", "m1": 5, "m2": 10}]
    out = shape_chart(rows, ["m1", "m2"], False, False, 10)
    assert out["labels"] == ["B", "A"]
    assert [(d["measure"], d["data"]) for d in out["datasets"]] == [("m1", [5, 1]), ("m2", [10, 90])]


def test_shape_chart_breakdown_with_other():
    rows = [
        {"label": date(2026, 1, 1), "series": "x", "m": 10},
        {"label": date(2026, 1, 1), "series": "y", "m": 5},
        {"label": date(2026, 2, 1), "series": "z", "m": 1},
    ]
    out = shape_chart(rows, ["m"], True, True, 2)
    assert out["labels"] == ["2026-01-01", "2026-02-01"]
    assert [d["series"] for d in out["datasets"]] == ["x", "y", OTHER_LABEL]
    assert out["datasets"][2]["data"] == [0, 1]


def test_shape_chart_breakdown_multiple_measures_ranked_by_first():
    rows = [
        {"label": "Jan", "series": "x", "m1": 1, "m2": 100},
        {"label": "Jan", "series": "y", "m1": 9, "m2": 1},
    ]
    out = shape_chart(rows, ["m1", "m2"], True, True, 1)
    assert [(d["measure"], d["series"], d["data"]) for d in out["datasets"]] == [
        ("m1", "y", [9]), ("m1", OTHER_LABEL, [1]), ("m2", "y", [1]), ("m2", OTHER_LABEL, [100])]
