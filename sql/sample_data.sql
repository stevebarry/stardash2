-- Optional demo data for trying the BI Dashboard.
-- Creates schema "demo", a table of random sales, the view demo.sales_demo,
-- and a role "sales_reader" that can be assigned to dashboards.
-- Run as a superuser or database owner:  psql -d bi -f sql/sample_data.sql

CREATE SCHEMA IF NOT EXISTS demo;

DROP TABLE IF EXISTS demo.sales CASCADE;
CREATE TABLE demo.sales AS
SELECT
    d::date                                                     AS sale_date,
    (ARRAY['North', 'South', 'East', 'West'])[1 + floor(random() * 4)::int]                  AS region,
    (ARRAY['Hardware', 'Software', 'Services'])[1 + floor(random() * 3)::int]                AS product_line,
    (ARRAY['Online', 'Retail', 'Partner'])[1 + floor(random() * 3)::int]                     AS channel,
    round((random() * 900 + 100)::numeric, 2)                   AS revenue,
    round((random() * 500 + 50)::numeric, 2)                    AS cost,
    1 + floor(random() * 20)::int                               AS units
FROM generate_series(current_date - interval '730 days', current_date, interval '1 day') AS d,
     generate_series(1, 25);

CREATE OR REPLACE VIEW demo.sales_demo AS
SELECT
    sale_date    AS date_sale,
    region,
    product_line,
    channel,
    revenue      AS euro_revenue,
    cost         AS euro_cost,
    units        AS ms_units,
    1            AS ms_orders
FROM demo.sales;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sales_reader') THEN
        CREATE ROLE sales_reader NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA demo TO sales_reader;
GRANT SELECT ON demo.sales_demo TO sales_reader;
