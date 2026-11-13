"""CRUD for the configuration tables (dashboards, roles, items)."""
from psycopg2 import sql
from psycopg2.extras import Json

from app.db import run_query, table


def list_dashboards():
    """All dashboards with their roles."""
    return run_query(
        sql.SQL(
            "SELECT d.id, d.name, d.view_schema, d.view_name, d.created_by, d.created_at, "
            "COALESCE(array_agg(r.role_name ORDER BY r.role_name) "
            "FILTER (WHERE r.role_name IS NOT NULL), '{{}}') AS roles "
            "FROM {} d LEFT JOIN {} r ON r.dashboard_id = d.id "
            "GROUP BY d.id ORDER BY d.name"
        ).format(table("dashboard"), table("dashboard_role")),
        activity="List dashboards",
    )


def get_dashboard(dashboard_id):
    return run_query(
        sql.SQL(
            "SELECT d.id, d.name, d.view_schema, d.view_name, d.created_by, d.created_at, "
            "COALESCE(array_agg(r.role_name) FILTER (WHERE r.role_name IS NOT NULL), '{{}}') AS roles "
            "FROM {} d LEFT JOIN {} r ON r.dashboard_id = d.id "
            "WHERE d.id = %s GROUP BY d.id"
        ).format(table("dashboard"), table("dashboard_role")),
        (dashboard_id,),
        activity="Get dashboard",
        fetch="one",
    )


def create_dashboard(name, view_schema, view_name, roles, created_by):
    row = run_query(
        sql.SQL(
            "INSERT INTO {} (name, view_schema, view_name, created_by) "
            "VALUES (%s, %s, %s, %s) RETURNING id"
        ).format(table("dashboard")),
        (name, view_schema, view_name, created_by),
        activity="Create dashboard",
        dashboard_name=name,
        fetch="one",
    )
    for role in roles:
        run_query(
            sql.SQL("INSERT INTO {} (dashboard_id, role_name) VALUES (%s, %s)").format(
                table("dashboard_role")
            ),
            (row["id"], role),
            activity=f"Grant dashboard to role {role}",
            dashboard_name=name,
            fetch=None,
        )
    return row["id"]


def delete_dashboard(dashboard_id, name):
    return run_query(
        sql.SQL("DELETE FROM {} WHERE id = %s").format(table("dashboard")),
        (dashboard_id,),
        activity="Delete dashboard",
        dashboard_name=name,
        fetch=None,
    )


def list_items(dashboard_id, dashboard_name):
    return run_query(
        sql.SQL(
            "SELECT id, item_type, config, width, position FROM {} "
            "WHERE dashboard_id = %s ORDER BY position, id"
        ).format(table("dashboard_item")),
        (dashboard_id,),
        activity="List dashboard items",
        dashboard_name=dashboard_name,
    )


def get_item(item_id):
    return run_query(
        sql.SQL("SELECT id, dashboard_id, item_type, config, width, position FROM {} WHERE id = %s").format(
            table("dashboard_item")
        ),
        (item_id,),
        activity="Get dashboard item",
        fetch="one",
    )


def create_item(dashboard_id, dashboard_name, item_type, item_config, width):
    return run_query(
        sql.SQL(
            "INSERT INTO {t} (dashboard_id, item_type, config, width, position) "
            "VALUES (%s, %s, %s, %s, "
            "(SELECT COALESCE(MAX(position), 0) + 1 FROM {t} WHERE dashboard_id = %s)) "
            "RETURNING id, item_type, config, width, position"
        ).format(t=table("dashboard_item")),
        (dashboard_id, item_type, Json(item_config), width, dashboard_id),
        activity=f"Add {item_type} item",
        dashboard_name=dashboard_name,
        fetch="one",
    )


def update_item(item_id, dashboard_name, item_config=None, width=None):
    sets, params = [], []
    if item_config is not None:
        sets.append(sql.SQL("config = %s"))
        params.append(Json(item_config))
    if width is not None:
        sets.append(sql.SQL("width = %s"))
        params.append(width)
    if not sets:
        return None
    params.append(item_id)
    return run_query(
        sql.SQL("UPDATE {} SET {} WHERE id = %s RETURNING id, item_type, config, width, position").format(
            table("dashboard_item"), sql.SQL(", ").join(sets)
        ),
        params,
        activity="Update dashboard item",
        dashboard_name=dashboard_name,
        fetch="one",
    )


def delete_item(item_id, dashboard_name):
    return run_query(
        sql.SQL("DELETE FROM {} WHERE id = %s").format(table("dashboard_item")),
        (item_id,),
        activity="Delete dashboard item",
        dashboard_name=dashboard_name,
        fetch=None,
    )


def list_views():
    """Views (and materialized views) available as dashboard sources."""
    return run_query(
        "SELECT schemaname AS schema, viewname AS name FROM pg_views "
        "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
        "UNION SELECT schemaname, matviewname FROM pg_matviews "
        "ORDER BY 1, 2",
        activity="List source views",
    )


def list_roles():
    """Non-system database roles that can be granted dashboard access."""
    return run_query(
        "SELECT rolname FROM pg_roles WHERE rolname NOT LIKE 'pg\\_%' ORDER BY rolname",
        activity="List database roles",
    )
