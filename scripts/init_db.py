"""Create the BI Dashboard configuration schema and tables.

Usage (from the project root):
    python scripts/init_db.py
"""
import os
import re
import sys

import psycopg2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402


def main():
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", config.CONFIG_SCHEMA):
        sys.exit(f"Invalid CONFIG_SCHEMA name: {config.CONFIG_SCHEMA!r}")

    with open(os.path.join(ROOT, "sql", "schema.sql"), encoding="utf-8") as f:
        ddl = f.read().format(schema=config.CONFIG_SCHEMA)

    conn = psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    try:
        with conn, conn.cursor() as cur:
            cur.execute(ddl)
        print(f"Schema '{config.CONFIG_SCHEMA}' initialised in database '{config.DB_NAME}'.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
