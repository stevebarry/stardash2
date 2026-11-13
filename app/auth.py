"""Authentication against PostgreSQL and role-based authorisation."""
from functools import wraps

import psycopg2
from flask import session, redirect, url_for, request, jsonify, abort

import config
from app.db import run_query


def verify_credentials(username, password):
    """Return True if the username/password can open a PostgreSQL connection."""
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            dbname=config.DB_NAME,
            user=username,
            password=password,
            connect_timeout=10,
        )
    except psycopg2.OperationalError:
        return False
    conn.close()
    return True


def lookup_roles(username):
    """All roles the user is a member of, directly or indirectly (including itself)."""
    rows = run_query(
        "SELECT rolname FROM pg_roles WHERE pg_has_role(%s, oid, 'member') ORDER BY rolname",
        (username,),
        activity="Look up user roles",
        user=username,
    )
    return [r["rolname"] for r in rows]


def login_user(username, roles):
    session.clear()
    session["username"] = username
    session["roles"] = roles
    session["is_admin"] = config.ADMIN_ROLE in roles


def current_roles():
    return set(session.get("roles", []))


def is_admin():
    return bool(session.get("is_admin"))


def can_access(dashboard_roles):
    """True if the current user may read a dashboard with the given role list."""
    return is_admin() or bool(current_roles() & set(dashboard_roles))


def _wants_json():
    return request.path.startswith("/api/")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            if _wants_json():
                return jsonify(error="Not logged in"), 401
            return redirect(url_for("views.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not is_admin():
            abort(403)
        return view(*args, **kwargs)
    return wrapped
