-- BI Dashboard configuration schema.
-- {schema} is replaced with config.CONFIG_SCHEMA by scripts/init_db.py.

CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.dashboard (
    id           serial PRIMARY KEY,
    name         text NOT NULL UNIQUE,
    view_schema  text NOT NULL,
    view_name    text NOT NULL,
    created_by   text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {schema}.dashboard_role (
    dashboard_id integer NOT NULL REFERENCES {schema}.dashboard(id) ON DELETE CASCADE,
    role_name    text NOT NULL,
    PRIMARY KEY (dashboard_id, role_name)
);

CREATE TABLE IF NOT EXISTS {schema}.dashboard_item (
    id           serial PRIMARY KEY,
    dashboard_id integer NOT NULL REFERENCES {schema}.dashboard(id) ON DELETE CASCADE,
    item_type    text NOT NULL CHECK (item_type IN ('kpi', 'chart', 'table')),
    config       jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    width        text NOT NULL DEFAULT 'half' CHECK (width IN ('half', 'full')),
    position     integer NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS dashboard_item_dashboard_idx
    ON {schema}.dashboard_item (dashboard_id, position);

CREATE TABLE IF NOT EXISTS {schema}.query_log (
    id                   bigserial PRIMARY KEY,
    start_time           timestamptz NOT NULL,
    end_time             timestamptz NOT NULL,
    duration_seconds     numeric(12, 6) NOT NULL,
    activity_description text,
    "user"               text,
    dashboard_name       text
);

CREATE INDEX IF NOT EXISTS query_log_start_idx ON {schema}.query_log (start_time);
