"""Column classification and safe SQL generation for a dashboard's source view.

Column naming conventions:
    euro_*  facts holding euro values (summed)
    ms_*    additive measures (summed)
    date_*  main date attribute (first one found)
    other   attributes (x-axis / breakdown / filter)
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from psycopg2 import sql

import config
from app.db import run_query

DATE_GRAINS = ("day", "week", "month", "quarter", "year")
BLANK_LABEL = "(blank)"
OTHER_LABEL = "Other"


def classify_columns(columns):
    """columns: iterable of column names in view order."""
    result = {"euro": [], "measures": [], "date": None, "dates": [], "attributes": []}
    for name in columns:
        lower = name.lower()
        if lower.startswith("euro_"):
            result["euro"].append(name)
        elif lower.startswith("ms_"):
            result["measures"].append(name)
        elif lower.startswith("date_"):
            result["dates"].append(name)
        else:
            result["attributes"].append(name)
    if result["dates"]:
        result["date"] = result["dates"][0]
    return result


def to_json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class DataSource:
    def __init__(self, view_schema, view_name, columns, dashboard_name=None):
        self.view_schema = view_schema
        self.view_name = view_name
        self.dashboard_name = dashboard_name
        self.cols = classify_columns(columns)

    @classmethod
    def load(cls, dashboard):
        rows = run_query(
            "SELECT a.attname FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped "
            "ORDER BY a.attnum",
            (dashboard["view_schema"], dashboard["view_name"]),
            activity="Read view columns",
            dashboard_name=dashboard["name"],
        )
        if not rows:
            raise ValueError(f"View {dashboard['view_schema']}.{dashboard['view_name']} not found")
        return cls(dashboard["view_schema"], dashboard["view_name"],
                   [r["attname"] for r in rows], dashboard["name"])

    # ---- validation -------------------------------------------------------

    @property
    def all_measures(self):
        return self.cols["euro"] + self.cols["measures"]

    def is_euro(self, measure):
        return measure in self.cols["euro"]

    def _measure(self, name):
        if name not in self.all_measures:
            raise ValueError(f"Unknown measure: {name!r}")
        return sql.Identifier(name)

    def _attribute(self, name):
        if name not in self.cols["attributes"]:
            raise ValueError(f"Unknown attribute: {name!r}")
        return sql.Identifier(name)

    def _view(self):
        return sql.Identifier(self.view_schema, self.view_name)

    def _group_expr(self, name, grain):
        """Expression for an x-axis/breakdown column; the date column is truncated to grain."""
        if name and name == self.cols["date"]:
            if grain not in DATE_GRAINS:
                raise ValueError(f"Unknown date grain: {grain!r}")
            return sql.SQL("date_trunc({}, {})::date").format(sql.Literal(grain), sql.Identifier(name))
        return self._attribute(name)

    # ---- SQL builders (no DB access) ------------------------------------------

    def build_where(self, filters=None, start=None, end=None):
        clauses, params = [], []
        for attr, values in (filters or {}).items():
            if not values:
                continue
            ident = self._attribute(attr)
            values = list(values)
            parts = []
            non_blank = [v for v in values if v != BLANK_LABEL]
            if non_blank:
                parts.append(sql.SQL("{}::text = ANY(%s)").format(ident))
                params.append(non_blank)
            if BLANK_LABEL in values:
                parts.append(sql.SQL("{} IS NULL").format(ident))
            clauses.append(sql.SQL("(") + sql.SQL(" OR ").join(parts) + sql.SQL(")"))
        date_col = self.cols["date"]
        if date_col and start:
            clauses.append(sql.SQL("{} >= %s").format(sql.Identifier(date_col)))
            params.append(start)
        if date_col and end:
            clauses.append(sql.SQL("{} < %s").format(sql.Identifier(date_col)))
            params.append(end + timedelta(days=1))
        if not clauses:
            return sql.SQL(""), params
        return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses), params

    def build_kpi_query(self, measure, where):
        return sql.SQL("SELECT SUM({m}) AS value FROM {v}{w}").format(
            m=self._measure(measure), v=self._view(), w=where)

    def build_chart_query(self, x_axis, measures, where, breakdown=None, grain="month"):
        if not measures:
            raise ValueError("A chart needs at least one measure")
        select = [sql.SQL("{} AS label").format(self._group_expr(x_axis, grain))]
        if breakdown:
            select.append(sql.SQL("{} AS series").format(self._group_expr(breakdown, grain)))
        # measure columns keep their own names (euro_/ms_ prefixes cannot clash with label/series)
        for m in measures:
            select.append(sql.SQL("SUM({c}) AS {c}").format(c=self._measure(m)))
        group = sql.SQL("1, 2") if breakdown else sql.SQL("1")
        return sql.SQL("SELECT {s} FROM {v}{w} GROUP BY {g} ORDER BY {g}").format(
            s=sql.SQL(", ").join(select), v=self._view(), w=where, g=group)

    def build_table_query(self, dimensions, measures, where, limit):
        if not measures and not dimensions:
            raise ValueError("A table needs at least one column")
        select = []
        for d in dimensions:
            if d == self.cols["date"]:
                select.append(sql.SQL("{c}::date AS {c}").format(c=sql.Identifier(d)))
            else:
                select.append(self._attribute(d))
        for m in measures:
            select.append(sql.SQL("SUM({c}) AS {c}").format(c=self._measure(m)))
        query = sql.SQL("SELECT {} FROM {}").format(sql.SQL(", ").join(select), self._view()) + where
        if dimensions:
            positions = sql.SQL(", ").join(sql.Literal(i + 1) for i in range(len(dimensions)))
            query += sql.SQL(" GROUP BY ") + positions
            if measures:
                query += sql.SQL(" ORDER BY {} DESC NULLS LAST").format(sql.Literal(len(dimensions) + 1))
            else:
                query += sql.SQL(" ORDER BY ") + positions
        return query + sql.SQL(" LIMIT {}").format(sql.Literal(int(limit)))

    def build_distinct_query(self, attr, limit):
        ident = self._attribute(attr)
        return sql.SQL("SELECT DISTINCT {a}::text AS value FROM {v} ORDER BY 1 LIMIT {n}").format(
            a=ident, v=self._view(), n=sql.Literal(int(limit)))

    # ---- execution ----------------------------------------------------------------

    def _run(self, query, params, activity, fetch="all"):
        return run_query(query, params, activity=activity, dashboard_name=self.dashboard_name, fetch=fetch)

    def filter_values(self):
        values = {}
        for attr in self.cols["attributes"]:
            rows = self._run(self.build_distinct_query(attr, config.MAX_FILTER_VALUES), None,
                             f"Filter values for {attr}")
            values[attr] = [BLANK_LABEL if r["value"] is None else r["value"] for r in rows]
        return values

    def kpi(self, measure, filters, start, end, prev_range=None):
        where, params = self.build_where(filters, start, end)
        row = self._run(self.build_kpi_query(measure, where), params, f"KPI {measure}", fetch="one")
        result = {"value": to_json_value(row["value"]), "previous": None, "is_euro": self.is_euro(measure)}
        if prev_range:
            where, params = self.build_where(filters, *prev_range)
            prev = self._run(self.build_kpi_query(measure, where), params,
                             f"KPI {measure} previous period", fetch="one")
            result["previous"] = to_json_value(prev["value"])
            result["previous_start"] = prev_range[0].isoformat()
            result["previous_end"] = prev_range[1].isoformat()
        return result

    def chart(self, x_axis, measures, filters, start, end, breakdown=None, grain="month"):
        if breakdown == x_axis:
            breakdown = None
        where, params = self.build_where(filters, start, end)
        rows = self._run(self.build_chart_query(x_axis, measures, where, breakdown, grain), params,
                         f"Chart {', '.join(measures)} by {x_axis}" + (f" / {breakdown}" if breakdown else ""))
        result = shape_chart(rows, measures, bool(breakdown), x_axis == self.cols["date"],
                             config.MAX_BREAKDOWN_SERIES)
        for ds in result["datasets"]:
            ds["is_euro"] = self.is_euro(ds["measure"])
        return result

    def table(self, dimensions, measures, filters, start, end):
        where, params = self.build_where(filters, start, end)
        rows = self._run(self.build_table_query(dimensions, measures, where, config.MAX_TABLE_ROWS),
                         params, "Table")
        columns = list(dimensions) + list(measures)
        return {
            "columns": columns,
            "euro_columns": [m for m in measures if self.is_euro(m)],
            "measure_columns": list(measures),
            "rows": [[to_json_value(r[c]) for c in columns] for r in rows],
        }


def _label(value):
    return BLANK_LABEL if value is None else str(to_json_value(value))


def shape_chart(rows, measures, has_breakdown, is_date_group, max_series):
    """Turn (label[, series], measure...) rows into {labels, datasets:[{measure, series, data}]}.

    One dataset per measure, or per measure and breakdown value. Breakdown values are ranked
    by the first measure; values beyond max_series are summed into "Other".
    """
    first = measures[0]
    labels, cells = [], {}  # cells[label][series][measure] = value
    for r in rows:
        label = _label(r["label"])
        series = _label(r["series"]) if has_breakdown else None
        if label not in cells:
            labels.append(label)
            cells[label] = {}
        bucket = cells[label].setdefault(series, {})
        for m in measures:
            bucket[m] = bucket.get(m, 0) + (to_json_value(r[m]) or 0)

    def total(label, m):
        return sum(v.get(m, 0) for v in cells[label].values())

    if not is_date_group:
        labels.sort(key=lambda l: total(l, first), reverse=True)

    if not has_breakdown:
        return {"labels": labels, "datasets": [
            {"measure": m, "series": None, "data": [total(l, m) for l in labels]} for m in measures]}

    totals = {}
    for by_series in cells.values():
        for s, vals in by_series.items():
            totals[s] = totals.get(s, 0) + vals.get(first, 0)
    ranked = sorted(totals, key=lambda s: totals[s], reverse=True)
    keep = ranked[:max_series]
    has_other = len(ranked) > max_series
    kept = set(keep)

    datasets = []
    for m in measures:
        for s in keep:
            datasets.append({"measure": m, "series": s,
                             "data": [cells[l].get(s, {}).get(m, 0) for l in labels]})
        if has_other:
            datasets.append({"measure": m, "series": OTHER_LABEL, "data": [
                sum(v.get(m, 0) for s, v in cells[l].items() if s not in kept) for l in labels]})
    return {"labels": labels, "datasets": datasets}
