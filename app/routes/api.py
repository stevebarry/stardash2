"""JSON API used by the dashboard list and dashboard screens.

Write endpoints only accept application/json bodies, which cross-site HTML forms
cannot send without a CORS preflight; together with SameSite=Lax session cookies
this protects them against CSRF.
"""
import re
from datetime import date

import psycopg2
import psycopg2.errors
from flask import Blueprint, jsonify, request, session, abort, send_file

from app import auth, repository, export
from app.datasource import DataSource, DATE_GRAINS
from app.periods import PERIODS, period_range, previous_range, periods_for_ui, pct_change

bp = Blueprint("api", __name__)

CHART_TYPES = ("bar", "stacked_bar", "horizontal_bar", "line", "area", "pie", "doughnut")
ITEM_TYPES = ("kpi", "chart", "table")


class BadRequest(Exception):
    pass


@bp.errorhandler(BadRequest)
@bp.errorhandler(ValueError)
def bad_request(e):
    return jsonify(error=str(e)), 400


@bp.errorhandler(psycopg2.Error)
def db_error(e):
    return jsonify(error=f"Database error: {e.pgerror or e}"), 500


@bp.errorhandler(export.ExportUnavailable)
def export_unavailable(e):
    return jsonify(error=str(e)), 503


def _json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise BadRequest("Expected a JSON object body")
    return body


def _accessible_dashboard(dashboard_id):
    dash = repository.get_dashboard(dashboard_id)
    if not dash:
        abort(404)
    if not auth.can_access(dash["roles"]):
        abort(403)
    return dash


def _item_with_dashboard(item_id):
    item = repository.get_item(item_id)
    if not item:
        abort(404)
    return item, _accessible_dashboard(item["dashboard_id"])


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise BadRequest(f"Invalid date: {value!r}")


def _resolve_dates(body):
    """Return (start, end, previous_range_or_None) from a request body."""
    period = body.get("period") or None
    if period:
        if period not in PERIODS:
            raise BadRequest(f"Unknown period: {period!r}")
        start, end = period_range(period)
        return start, end, previous_range(period)
    return _parse_date(body.get("start")), _parse_date(body.get("end")), None


def _filters(body):
    filters = body.get("filters") or {}
    if not isinstance(filters, dict):
        raise BadRequest("filters must be an object")
    return {k: [str(v) for v in vals] for k, vals in filters.items() if isinstance(vals, list) and vals}


def _validate_item(ds, item_type, cfg):
    """Check an item config against the view's columns and return a clean copy."""
    if item_type not in ITEM_TYPES:
        raise BadRequest(f"Unknown item type: {item_type!r}")
    if not isinstance(cfg, dict):
        raise BadRequest("config must be an object")
    title = str(cfg.get("title") or "").strip()[:200]
    measures = ds.all_measures
    group_cols = ds.cols["attributes"] + ([ds.cols["date"]] if ds.cols["date"] else [])

    if item_type == "kpi":
        if cfg.get("measure") not in measures:
            raise BadRequest("Choose a valid measure")
        return {"title": title, "measure": cfg["measure"]}

    if item_type == "chart":
        if cfg.get("chart_type") not in CHART_TYPES:
            raise BadRequest("Choose a valid chart type")
        x_axis = cfg.get("x_axis") or cfg.get("group_by")  # charts saved before the x-axis rename
        if x_axis not in group_cols:
            raise BadRequest("Choose a valid x-axis field")
        chosen = cfg.get("measures")
        if chosen is None and cfg.get("measure"):
            chosen = [cfg["measure"]]  # charts saved before multi-measure support
        if not isinstance(chosen, list) or not chosen:
            raise BadRequest("Choose at least one measure")
        if any(m not in measures for m in chosen):
            raise BadRequest("Choose valid measures")
        chosen = list(dict.fromkeys(chosen))
        breakdown = cfg.get("breakdown") or None
        if breakdown and breakdown not in group_cols:
            raise BadRequest("Choose a valid breakdown column")
        if cfg["chart_type"] in ("pie", "doughnut"):
            if len(chosen) > 1:
                raise BadRequest("Pie and doughnut charts show one measure - choose just one")
            breakdown = None
        grain = cfg.get("grain") or "month"
        if grain not in DATE_GRAINS:
            raise BadRequest("Choose a valid date grain")
        return {"title": title, "chart_type": cfg["chart_type"], "x_axis": x_axis,
                "breakdown": breakdown, "measures": chosen, "grain": grain}

    dims = [d for d in cfg.get("dimensions") or [] if d in group_cols]
    meas = [m for m in cfg.get("measures") or [] if m in measures]
    if not dims and not meas:
        raise BadRequest("Choose at least one column for the table")
    return {"title": title, "dimensions": dims, "measures": meas}


# ---- dashboard list -----------------------------------------------------------

@bp.get("/views")
@auth.admin_required
def views():
    return jsonify([f"{v['schema']}.{v['name']}" for v in repository.list_views()])


@bp.get("/roles")
@auth.admin_required
def roles():
    return jsonify([r["rolname"] for r in repository.list_roles()])


@bp.post("/dashboards")
@auth.admin_required
def create_dashboard():
    body = _json_body()
    name = str(body.get("name") or "").strip()
    view = str(body.get("view") or "")
    roles_ = [str(r) for r in body.get("roles") or []]
    if not name:
        raise BadRequest("Dashboard name is required")
    if not roles_:
        raise BadRequest("Select at least one role")
    available_views = {f"{v['schema']}.{v['name']}": v for v in repository.list_views()}
    if view not in available_views:
        raise BadRequest("Select a valid view")
    valid_roles = {r["rolname"] for r in repository.list_roles()}
    unknown = [r for r in roles_ if r not in valid_roles]
    if unknown:
        raise BadRequest(f"Unknown roles: {', '.join(unknown)}")
    v = available_views[view]
    try:
        new_id = repository.create_dashboard(name, v["schema"], v["name"], roles_, session["username"])
    except psycopg2.errors.UniqueViolation:
        raise BadRequest(f"A dashboard named {name!r} already exists")
    return jsonify(id=new_id), 201


@bp.delete("/dashboards/<int:dashboard_id>")
@auth.admin_required
def delete_dashboard(dashboard_id):
    dash = repository.get_dashboard(dashboard_id)
    if not dash:
        abort(404)
    repository.delete_dashboard(dashboard_id, dash["name"])
    return jsonify(ok=True)


# ---- dashboard screen ---------------------------------------------------------

@bp.get("/dashboards/<int:dashboard_id>/meta")
@auth.login_required
def dashboard_meta(dashboard_id):
    dash = _accessible_dashboard(dashboard_id)
    ds = DataSource.load(dash)
    return jsonify(
        dashboard={"id": dash["id"], "name": dash["name"],
                   "view": f"{dash['view_schema']}.{dash['view_name']}"},
        columns=ds.cols,
        items=repository.list_items(dashboard_id, dash["name"]),
        filter_values=ds.filter_values(),
        periods=periods_for_ui(),
        chart_types=CHART_TYPES,
        grains=DATE_GRAINS,
    )


@bp.post("/dashboards/<int:dashboard_id>/items")
@auth.login_required
def create_item(dashboard_id):
    dash = _accessible_dashboard(dashboard_id)
    body = _json_body()
    ds = DataSource.load(dash)
    item_type = body.get("item_type")
    cfg = _validate_item(ds, item_type, body.get("config"))
    width = body.get("width") if body.get("width") in ("half", "full") else "half"
    return jsonify(repository.create_item(dashboard_id, dash["name"], item_type, cfg, width)), 201


@bp.patch("/items/<int:item_id>")
@auth.login_required
def update_item(item_id):
    item, dash = _item_with_dashboard(item_id)
    body = _json_body()
    cfg = None
    if "config" in body:
        cfg = _validate_item(DataSource.load(dash), item["item_type"], body["config"])
    width = body.get("width")
    if width is not None and width not in ("half", "full"):
        raise BadRequest("width must be 'half' or 'full'")
    updated = repository.update_item(item_id, dash["name"], cfg, width)
    return jsonify(updated or item)


@bp.delete("/items/<int:item_id>")
@auth.login_required
def delete_item(item_id):
    _, dash = _item_with_dashboard(item_id)
    repository.delete_item(item_id, dash["name"])
    return jsonify(ok=True)


@bp.post("/dashboards/<int:dashboard_id>/data")
@auth.login_required
def item_data(dashboard_id):
    dash = _accessible_dashboard(dashboard_id)
    body = _json_body()
    ds = DataSource.load(dash)
    item_type = body.get("item_type")
    cfg = _validate_item(ds, item_type, body.get("config"))
    filters = _filters(body)
    start, end, prev = _resolve_dates(body)

    if item_type == "kpi":
        result = ds.kpi(cfg["measure"], filters, start, end, prev)
        result["pct_change"] = pct_change(result["value"], result["previous"]) if prev else None
    elif item_type == "chart":
        result = ds.chart(cfg["x_axis"], cfg["measures"], filters, start, end,
                          cfg["breakdown"], cfg["grain"])
    else:
        result = ds.table(cfg["dimensions"], cfg["measures"], filters, start, end)
    result["start"] = start.isoformat() if start else None
    result["end"] = end.isoformat() if end else None
    return jsonify(result)


@bp.post("/dashboards/<int:dashboard_id>/export")
@auth.login_required
def export_dashboard(dashboard_id):
    dash = _accessible_dashboard(dashboard_id)
    fmt = request.args.get("format", "pdf")
    if fmt not in ("pdf", "docx"):
        raise BadRequest("format must be pdf or docx")
    body = _json_body()
    items = body.get("items") or []
    filter_lines = [str(s) for s in body.get("filter_summary") or []]
    builder = export.build_pdf if fmt == "pdf" else export.build_docx
    buf = builder(dash["name"], filter_lines, items, session["username"])
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", dash["name"]).strip("_") or "dashboard"
    mimetype = ("application/pdf" if fmt == "pdf" else
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return send_file(buf, mimetype=mimetype, as_attachment=True, download_name=f"{safe_name}.{fmt}")
