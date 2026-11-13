"""Application configuration for the BI Dashboard.

Edit these values for your environment before running scripts/init_db.py.
"""

# PostgreSQL service connection used for configuration and dashboard queries
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "test"
DB_USER = "postgres"
DB_PASSWORD = "steve"

# Schema that holds the application's configuration tables
CONFIG_SCHEMA = "stardash"

# Database role allowed to create/delete dashboards (and read all of them)
ADMIN_ROLE = "role_bi_admin"

# Flask session signing key - set to a long random string in production
SECRET_KEY = "54564/*/*/454sdfads fsdfsd tgadrsfg dfgdf gdfsg df52154df5sfg45sd4g54"

# Connection pool size for the service connection
DB_POOL_MIN = 1
DB_POOL_MAX = 10

# Maximum distinct values offered in an attribute filter drop-down
MAX_FILTER_VALUES = 500

# Maximum number of breakdown series in a chart (remaining values grouped as "Other")
MAX_BREAKDOWN_SERIES = 10

# Maximum rows returned for a table widget
MAX_TABLE_ROWS = 1000
