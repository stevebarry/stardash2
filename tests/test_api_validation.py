import pytest

from app.datasource import DataSource
from app.routes.api import BadRequest, _validate_item


@pytest.fixture
def ds():
    return DataSource("demo", "sales_demo", ["date_sale", "region", "euro_revenue", "ms_units"], "Sales")


def chart(**overrides):
    cfg = {"chart_type": "bar", "x_axis": "region", "measures": ["euro_revenue"]}
    cfg.update(overrides)
    return cfg


def test_chart_with_several_measures(ds):
    out = _validate_item(ds, "chart", chart(measures=["euro_revenue", "ms_units", "euro_revenue"]))
    assert out["measures"] == ["euro_revenue", "ms_units"]
    assert out["grain"] == "month" and out["breakdown"] is None


def test_chart_saved_with_single_measure_and_group_by_still_valid(ds):
    cfg = {"chart_type": "line", "group_by": "date_sale", "measure": "ms_units", "grain": "week"}
    out = _validate_item(ds, "chart", cfg)
    assert out["measures"] == ["ms_units"]
    assert out["x_axis"] == "date_sale" and out["grain"] == "week" and "group_by" not in out


@pytest.mark.parametrize("grain", ["day", "week", "month", "quarter", "year"])
def test_chart_date_x_axis_accepts_each_subdivision(ds, grain):
    assert _validate_item(ds, "chart", chart(x_axis="date_sale", grain=grain))["grain"] == grain


@pytest.mark.parametrize("cfg", [chart(x_axis="ms_units"), chart(x_axis=None), chart(x_axis="date_sale", grain="decade")])
def test_chart_rejects_bad_x_axis(ds, cfg):
    with pytest.raises(BadRequest):
        _validate_item(ds, "chart", cfg)


@pytest.mark.parametrize("measures", [[], None, "ms_units", ["region"], ["nope"]])
def test_chart_rejects_bad_measures(ds, measures):
    with pytest.raises(BadRequest):
        _validate_item(ds, "chart", chart(measures=measures))


def test_pie_takes_one_measure_and_no_breakdown(ds):
    with pytest.raises(BadRequest):
        _validate_item(ds, "chart", chart(chart_type="pie", measures=["euro_revenue", "ms_units"]))
    out = _validate_item(ds, "chart", chart(chart_type="doughnut", breakdown="date_sale"))
    assert out["breakdown"] is None


def test_kpi_and_table_unchanged(ds):
    assert _validate_item(ds, "kpi", {"measure": "ms_units"}) == {"title": "", "measure": "ms_units"}
    assert _validate_item(ds, "table", {"dimensions": ["region", "bogus"], "measures": ["ms_units"]}) == \
        {"title": "", "dimensions": ["region"], "measures": ["ms_units"]}
