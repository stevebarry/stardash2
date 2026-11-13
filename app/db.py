"""Database access. Every query goes through run_query(), which logs it to query_log."""
from datetime import datetime, timezone
import logging

import psycopg2
import psycopg2.extras
from psycopg2 import sql
from psycopg2.pool import ThreadedConnectionPool

import config

log = logging.getLogger(__name__)

_pool = None


def init_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            config.DB_POOL_MIN,
            config.DB_POOL_MAX,
            host=config.DB_HOST,
            port=config.DB_PORT,
            dbname=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
        )
    return _pool


def table(name):
    """Qualified identifier for a configuration table."""
    return sql.Identifier(config.CONFIG_SCHEMA, name)


def _current_user():
    try:
        from flask import session, has_request_context
        if has_request_context():
            return session.get("username")
    except Exception:
        pass
    return None


def _log_query(conn, start, end, activity, user, dashboard_name):
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    'INSERT INTO {} (start_time, end_time, duration_seconds, '
                    'activity_description, "user", dashboard_name) '
                    'VALUES (%s, %s, %s, %s, %s, %s)'
                ).format(table("query_log")),
                (start, end, (end - start).total_seconds(), activity, user, dashboard_name),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("Failed to write query log")


def run_query(query, params=None, activity="", dashboard_name=None, fetch="all", user=None):
    """Execute a query on the service connection and log it.

    fetch: "all" -> list of dict rows, "one" -> dict or None, None -> rowcount.
    """
    user = user or _current_user()
    pool = init_pool()
    conn = pool.getconn()
    start = datetime.now(timezone.utc)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            if fetch == "all":
                result = cur.fetchall()
            elif fetch == "one":
                result = cur.fetchone()
            else:
                result = cur.rowcount
        conn.commit()
        return result
    except Exception:
        if not conn.closed:
            conn.rollback()
        raise
    finally:
        end = datetime.now(timezone.utc)
        if not conn.closed:
            _log_query(conn, start, end, activity, user, dashboard_name)
        else:
            log.error("Connection lost; query not logged: %s", activity)
        # discard connections broken by e.g. a server restart instead of reusing them
        pool.putconn(conn, close=bool(conn.closed))
