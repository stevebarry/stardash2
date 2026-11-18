# BI Dashboard

A web dashboard for business intelligence analysis, built with Flask on PostgreSQL. It runs under gunicorn behind NGINX on Ubuntu.

It is one of several self-contained applications sharing one NGINX instance. Each has its own URL prefix, folder, gunicorn service and socket. This one is served at **`http://<server>/stardash/`** (see [Sharing NGINX with other applications](#sharing-nginx-with-other-applications)).

- **Dashboard list:** shows the dashboards you are allowed to see. Admins can also create and delete dashboards.
- **Dashboard screen:**
  - Filters: a date period shortcut, start and end dates, and multi-select filters for each attribute column.
  - Widgets: KPIs (showing % change against the previous period when a period is selected), charts and tables.
  - Charts have an x-axis field (the main date can be split by day, week, month, quarter or year), a breakdown, one or more measures and a type, plus a full/half width toggle.
  - Export to PDF or Word, and download any table as CSV.

## How it works

| Concept | Implementation |
|---|---|
| Dashboard source | Each dashboard reads a single view (or materialized view) from anywhere in the database |
| Column conventions | `euro_*` = euro facts, `ms_*` = additive measures, `date_*` = main date (the first one found), anything else = attribute. Facts and measures are summed. |
| Configuration | Tables in the schema named by `CONFIG_SCHEMA` in `config.py`: `dashboard`, `dashboard_role`, `dashboard_item`, `query_log` |
| Login | Users sign in with their own PostgreSQL username and password. The app checks them by opening a connection, then reads the user's role memberships, including inherited ones. |
| Authorisation | Members of `ADMIN_ROLE` in `config.py` can create and delete dashboards and read every dashboard. Other users only see dashboards granted to at least one of their roles. |
| Data queries | Run on the service connection from `config.py` after the role check passes |
| Query log | Every database query is logged to `query_log` with `start_time`, `end_time`, `duration_seconds`, `activity_description`, `user` and `dashboard_name` |

## Project layout

```
config.py              URL prefix, database credentials, config schema, admin role, secret key
wsgi.py                WSGI entry point (gunicorn wsgi:app)
gunicorn.conf.py       gunicorn settings
app/                   Flask application (routes, templates, static JS/CSS)
sql/schema.sql         configuration tables
sql/sample_data.sql    optional demo view demo.sales_demo and role sales_reader
scripts/init_db.py     creates the configuration schema and tables
deploy/                shared NGINX server block, this app's NGINX locations, systemd unit (manual install)
ansible/               Ansible playbook for automated deployment
tests/                 unit tests (no database needed)
```

## Installation on Ubuntu

There are two ways to install: [automated with Ansible](#deployment-with-ansible), or manually with the steps below. To try the app on a Windows PC without NGINX or gunicorn, see [Running on Windows for testing](#running-on-windows-for-testing).

### 1. System packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx postgresql-client \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core   # Pango and fonts for PDF export (WeasyPrint)
```

### 2. Application files and virtualenv

```bash
sudo mkdir -p /opt/stardash
sudo cp -r . /opt/stardash
sudo chown -R $USER /opt/stardash
cd /opt/stardash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 3. Database setup

Connect to PostgreSQL as a superuser and create the service account and the admin role:

```sql
CREATE ROLE bi_app LOGIN PASSWORD 'change_me';   -- service account (DB_USER in config.py)
GRANT CREATE ON DATABASE bi TO bi_app;           -- lets init_db.py create the config schema
CREATE ROLE bi_admin NOLOGIN;                    -- ADMIN_ROLE in config.py
GRANT bi_admin TO alice;                         -- make an existing login user an admin
```

The service account needs `SELECT` on every view used as a dashboard source, for example:

```sql
GRANT USAGE ON SCHEMA sales TO bi_app;
GRANT SELECT ON sales.my_view TO bi_app;
```

Users who log in need the `CONNECT` privilege on the database (granted to `PUBLIC` by default), and `pg_hba.conf` must allow password authentication for them from the application server.

### 4. Configure

Edit `config.py`:

- `URL_PREFIX`: the URL path the app is served under (default `/stardash`). It must match the NGINX locations file. Use `""` to serve at the site root.
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`: the service connection
- `CONFIG_SCHEMA`: the schema for the configuration tables (default `bi_config`)
- `ADMIN_ROLE`: the role that can create and delete dashboards (default `bi_admin`)
- `SECRET_KEY`: set this to a long random value, for example from `python3 -c "import secrets; print(secrets.token_hex(32))"`

Because `config.py` holds credentials, restrict who can read it:

```bash
chmod 640 config.py
```

### 5. Create the configuration tables

```bash
venv/bin/python scripts/init_db.py
```

### 6. (Optional) Load demo data

```bash
psql -h localhost -U postgres -d bi -f sql/sample_data.sql
psql -h localhost -U postgres -d bi -c "GRANT USAGE ON SCHEMA demo TO bi_app; GRANT SELECT ON demo.sales_demo TO bi_app;"
```

This creates the view `demo.sales_demo` and the role `sales_reader`. To test as a non-admin user, run `GRANT sales_reader TO some_user;`.

## Starting the application

The application is not started automatically. Choose one of the options below.

### Option A: development server (quick test)

```bash
cd /opt/stardash
venv/bin/flask --app wsgi run --host 0.0.0.0 --port 5000
```

Open `http://<server>:5000/stardash/` and log in with a PostgreSQL user. (`http://<server>:5000/` redirects there.)

### Option B: gunicorn in the foreground

```bash
cd /opt/stardash
venv/bin/gunicorn -c gunicorn.conf.py wsgi:app
```

This listens on `127.0.0.1:8000`, with the app at `http://127.0.0.1:8000/stardash/`. The production service in Option C uses a Unix socket instead, so NGINX is configured for that.

### Option C: production (systemd + NGINX)

1. Install and start the gunicorn service. It listens on the Unix socket `/run/stardash/gunicorn.sock`, which systemd creates:

   ```bash
   sudo chown -R www-data:www-data /opt/stardash
   sudo cp deploy/systemd/stardash.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now stardash
   sudo systemctl status stardash
   ```

2. Configure NGINX. The shared server block is installed once per server. If another application already installed `/etc/nginx/sites-available/apps`, skip the first three commands:

   ```bash
   sudo cp deploy/nginx/apps.conf /etc/nginx/sites-available/apps        # shared server block (once per server)
   sudo ln -s /etc/nginx/sites-available/apps /etc/nginx/sites-enabled/
   sudo rm -f /etc/nginx/sites-enabled/default

   sudo mkdir -p /etc/nginx/app-locations
   sudo cp deploy/nginx/app-locations/stardash.conf /etc/nginx/app-locations/   # this application only
   sudo nginx -t && sudo systemctl reload nginx
   ```

3. Open `http://<server>/stardash/`. For production, add TLS, for example with certbot (`sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx`). certbot edits the shared server block, so all applications get TLS at once.

Logs: `journalctl -u stardash -f` for the app and `/var/log/nginx/` for NGINX.

### Sharing NGINX with other applications

This application is designed to live next to other applications on one NGINX server, each under its own path:

| | This application | Each other application |
|---|---|---|
| URL | `http://<server>/stardash/` | its own prefix, e.g. `/otherapp/` |
| Code | `/opt/stardash/` | its own folder |
| Service | `stardash.service` | its own unit |
| gunicorn | `unix:/run/stardash/gunicorn.sock` | its own socket, so no port numbers to coordinate |
| NGINX | `/etc/nginx/app-locations/stardash.conf` | its own `<app>.conf` |
| Session cookie | `stardash_session`, path `/stardash/` | its own cookie, so logins don't clash |

One shared `server {}` block (`/etc/nginx/sites-available/apps`) includes `/etc/nginx/app-locations/*.conf`. The server-wide settings (`listen`, `server_name`, TLS) belong there. Everything specific to an application belongs in its own locations file, so you can add, update or remove one application without touching the others. To remove this one: `sudo systemctl disable --now stardash`, delete `/etc/nginx/app-locations/stardash.conf`, then reload NGINX.

NGINX passes the full path, `/stardash/...`, to gunicorn. The app moves the prefix into the WSGI `SCRIPT_NAME` (see `PrefixMiddleware` in `app/__init__.py`), so every generated link, redirect, static file URL and JavaScript API call includes the prefix. To change the prefix, change `URL_PREFIX` in `config.py` and the three `/stardash` locations in the NGINX file together. With Ansible, setting `bi_url_prefix` changes both.

## Running on Windows for testing

For local testing you can run the app with Flask's built-in development server alone. Flask, psycopg2 and python-docx all work on Windows. gunicorn and NGINX are only needed in production; gunicorn does not run on Windows, but installing it from `requirements.txt` is harmless.

PDF export uses WeasyPrint, which needs the Pango libraries. Windows doesn't have them, so on a plain Windows install **Export → PDF** shows "PDF export needs the Pango libraries" while everything else, including Word export, works. To get PDF export on Windows, install Pango through MSYS2 ([WeasyPrint docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows)):

```powershell
winget install MSYS2.MSYS2                                   # installs to C:\msys64
C:\msys64\usr\bin\bash.exe -lc "pacman -S --needed --noconfirm mingw-w64-ucrt-x86_64-pango"
setx WEASYPRINT_DLL_DIRECTORIES C:\msys64\ucrt64\bin         # then open a new terminal
python -c "import weasyprint; print(weasyprint.__version__)" # in the venv: prints the version, not a libgobject error
```

Alternatively, run the app under WSL (Ubuntu) with the `apt` packages from the manual install.

The development server is single-user and not secure. Do not use it for production.

### 1. Prerequisites

- Python 3.10 or later from [python.org](https://www.python.org/downloads/windows/) (tick "Add python.exe to PATH"), or `winget install Python.Python.3.12`
- A PostgreSQL server you can reach: either the [Windows installer](https://www.postgresql.org/download/windows/) on the same PC, or an existing server

### 2. Virtualenv and dependencies (PowerShell)

```powershell
cd C:\path\to\21_Star_Dash2
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell refuses to run `Activate.ps1`, allow scripts for the current window only with `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again. In `cmd.exe`, use `venv\Scripts\activate.bat` instead.

### 3. Database

In `psql`, which the Windows installer puts under Start → PostgreSQL → SQL Shell, connect as `postgres` and run the statements from [Database setup](#3-database-setup). For example:

```sql
CREATE DATABASE bi;
CREATE ROLE bi_app LOGIN PASSWORD 'change_me';
GRANT CONNECT, CREATE ON DATABASE bi TO bi_app;
CREATE ROLE bi_admin NOLOGIN;
CREATE ROLE alice LOGIN PASSWORD 'alice_pw';
GRANT bi_admin TO alice;
```

Optionally load the demo data (`\i` needs forward slashes in the path):

```sql
\c bi
\i C:/path/to/21_Star_Dash2/sql/sample_data.sql
GRANT USAGE ON SCHEMA demo TO bi_app;
GRANT SELECT ON demo.sales_demo TO bi_app;
```

### 4. Configure and create the tables

Edit `config.py` with the database host, name, service account and password, `CONFIG_SCHEMA` and `ADMIN_ROLE` (see [Configure](#4-configure)). Then:

```powershell
python scripts\init_db.py
```

### 5. Run the development server

```powershell
flask --app wsgi run --debug
```

Open <http://127.0.0.1:5000/stardash/> and log in with a PostgreSQL login user (e.g. `alice` above). `--debug` reloads the app when you change code and shows tracebacks in the browser. Add `--port 8080` to use another port, or `--host 0.0.0.0` to allow other machines to connect. Windows Firewall will then ask for permission. Press `Ctrl+C` to stop.

If `flask` is not found, the virtualenv is not active: run `.\venv\Scripts\Activate.ps1`, or call `.\venv\Scripts\flask.exe` directly.

### Windows troubleshooting

| Symptom | Fix |
|---|---|
| `password authentication failed` | Test the same login with `psql -h <DB_HOST> -U <DB_USER> -d <DB_NAME>`. If it fails there too, reset the password with `ALTER ROLE ... PASSWORD '...'`. |
| `connection refused` / timeout | Check that the PostgreSQL service is running (`services.msc`). For a remote server, also check `listen_addresses` in `postgresql.conf`, a `host` line for your IP in `pg_hba.conf`, and port 5432 in the server's firewall. |
| Database in Windows, app in WSL (or the reverse) | `localhost` does not cross between them. Use the Windows host IP as seen from WSL (`ip route show default`, the address after `via`), and allow that subnet in `pg_hba.conf`. |
| Charts do not appear | Chart.js loads from cdn.jsdelivr.net, so internet access is needed (or vendor it; see [Offline servers](#offline-servers)). |
| Export fails with "Request Entity Too Large" | This does not happen with the Flask dev server, which allows 50 MB. It only applies behind NGINX (`client_max_body_size`). |

## Deployment with Ansible

The playbook in `ansible/` performs the manual installation and Option C above on one or more Ubuntu servers:

- installs the system packages
- copies the code and builds the virtualenv
- writes `config.py` and `gunicorn.conf.py` from variables
- runs `scripts/init_db.py`
- installs the systemd unit and this application's NGINX locations. It also creates the shared NGINX server block if no other application has created it yet.
- optionally sets up PostgreSQL (database, service account, admin role, grants, login users, sample data)

It is idempotent, so you can run it again to deploy new code or config changes. The service is restarted only when something changed.

### Requirements

- **Control machine:** Linux, macOS or WSL (Ansible does not run natively on Windows), with `ansible-core` 2.15 or later and `rsync`.
- **Targets:** Ubuntu 22.04 or 24.04, reachable over SSH by a user with sudo rights.

Install Ansible with pipx. On Ubuntu 23.04+ and Debian 12+, a bare `pip install` fails with `externally-managed-environment` (PEP 668):

```bash
sudo apt install -y pipx rsync      # macOS: brew install pipx rsync
pipx ensurepath                     # then open a new shell
pipx install ansible-core

cd ansible
ansible-galaxy collection install -r requirements.yml   # ansible.posix, community.postgresql, community.general
```

If you prefer a virtualenv instead of pipx:

```bash
python3 -m venv ~/.venvs/ansible
~/.venvs/ansible/bin/pip install ansible-core
source ~/.venvs/ansible/bin/activate
```

### Layout

```
ansible/
  ansible.cfg
  inventory.example.ini        copy to inventory.ini
  site.yml                     playbook: bi_database (optional), then bi_dashboard
  requirements.yml             Galaxy collections
  vault.example.yml            copy to group_vars/all/vault.yml and encrypt
  group_vars/all/main.yml      all settings, with defaults
  roles/bi_database/           PostgreSQL install, database, roles, grants, sample data
  roles/bi_dashboard/          app code, venv, config.py, gunicorn/systemd, NGINX, ufw, health check
```

### 1. Inventory

```bash
cp inventory.example.ini inventory.ini
```

List your server(s) under `[bi_dashboard]`. To deploy to the machine you are running Ansible on, use a local connection instead of SSH:

```ini
[bi_dashboard]
localhost ansible_connection=local
```

### 2. Secrets

```bash
cp vault.example.yml group_vars/all/vault.yml
# set vault_bi_db_password and vault_bi_secret_key (generate with: python3 -c "import secrets; print(secrets.token_hex(32))")
ansible-vault encrypt group_vars/all/vault.yml
```

The playbook refuses to run while either secret is still `change_me`, or if the secret key is shorter than 32 characters.

### 3. Settings

Edit `group_vars/all/main.yml`. The main choices are:

| Variable | Default | Meaning |
|---|---|---|
| `bi_manage_database` | `true` | Let the playbook create the database, service account (`bi_db_user`), admin role (`bi_admin_role`) and grants. Set to `false` if your DBA manages PostgreSQL; then follow [Database setup](#3-database-setup) by hand. |
| `bi_install_postgresql` | `true` | Install PostgreSQL on the app server (single-box install). Set to `false` to use an existing server at `bi_db_host`; the playbook then connects as `bi_db_superuser` with `vault_bi_db_superuser_password`, once per run. |
| `bi_db_host` / `bi_db_name` / `bi_db_user` | `localhost` / `bi` / `bi_app` | Written to `config.py` |
| `bi_config_schema` / `bi_admin_role` | `bi_config` / `bi_admin` | Written to `config.py` |
| `bi_db_login_users` | `[]` | Login users to create, each with `name` and `roles`; passwords come from `vault_bi_login_passwords` |
| `bi_admin_members` | `[]` | Existing users to add to the admin role |
| `bi_source_grants` | `[]` | Source views the service account may read, e.g. `[{schema: sales, views: [orders_v]}]` |
| `bi_load_sample_data` | `false` | Load `sql/sample_data.sql` once, and grant the service account access to `demo.sales_demo` |
| `bi_app_name` | `stardash` | Name used for the app folder (`/opt/stardash`), systemd service, socket directory (`/run/stardash`) and NGINX locations file |
| `bi_url_prefix` | `/stardash` | URL path of the app. Written to `config.py` (`URL_PREFIX`) and the NGINX locations file. |
| `bi_nginx_shared_site` / `bi_nginx_locations_dir` | `apps` / `/etc/nginx/app-locations` | Shared server block and the directory it includes. Use the same values for all the applications on the server. |
| `bi_server_name` / `bi_http_port` | `_` / `80` | NGINX `server_name` and `listen` port. Only used when the shared server block is first created. |
| `bi_gunicorn_workers` / `bi_gunicorn_threads` | `3` / `2` | gunicorn sizing |
| `bi_configure_ufw` | `false` | Allow OpenSSH and the HTTP port, then enable ufw |
| `bi_start_service` | `true` | Set to `false` to install everything but leave the service stopped and disabled. Start it later with `sudo systemctl enable --now stardash`. |

Example for a demo box with an admin and a reader:

```yaml
bi_load_sample_data: true
bi_db_login_users:
  - { name: alice, roles: [bi_admin] }
  - { name: bob,   roles: [sales_reader] }
```

with `vault_bi_login_passwords: {alice: "...", bob: "..."}` in the vault file.

### 4. Run

```bash
ansible-playbook -i inventory.ini site.yml --ask-vault-pass --check --diff   # dry run (a first run fails in check mode because packages are not yet installed)
ansible-playbook -i inventory.ini site.yml --ask-vault-pass
```

Passing `-i inventory.ini` explicitly avoids "skipping: no hosts matched" when `ansible.cfg` is ignored. Ansible ignores it in world-writable directories, which includes any `/mnt/c/...` path under WSL; you'll see a "world writable directory" warning when this happens. For WSL, the best fix is to clone the repo into your Linux home directory, e.g. `~/21_Star_Dash2`.

Useful variations:

```bash
ansible-playbook -i inventory.ini site.yml --ask-vault-pass --tags app        # code/config only, skip database setup
ansible-playbook -i inventory.ini site.yml --ask-vault-pass --tags database   # database setup only
ansible-playbook -i inventory.ini site.yml --ask-vault-pass --limit bi01.example.com
```

The last task requests `http://127.0.0.1/stardash/login` on each server and fails the run if the page does not return 200.

### What the playbook manages on the server

| Path | Source |
|---|---|
| `/opt/stardash/` | Project files synced with rsync (`.git`, `venv`, `tests`, `ansible` excluded); files removed from the project are removed here too |
| `/opt/stardash/config.py` | Template `config.py.j2`; mode 0640, group `www-data` |
| `/opt/stardash/gunicorn.conf.py` | Template `gunicorn.conf.py.j2` |
| `/opt/stardash/venv/` | `pip install -r requirements.txt` |
| `/etc/systemd/system/stardash.service` | Template `bi-dashboard.service.j2` (creates `/run/stardash/` for the gunicorn socket) |
| `/etc/nginx/app-locations/stardash.conf` | Template `nginx-locations.conf.j2`: this application's locations, checked with `nginx -t` before reload |
| `/etc/nginx/sites-available/apps` | Template `nginx-site.conf.j2`: the shared server block, **created only if missing** and never overwritten. If it exists but does not include `/etc/nginx/app-locations/*.conf`, the run stops with instructions. |

Make changes through the Ansible variables, not on the server: the next run overwrites `config.py`, `gunicorn.conf.py`, the systemd unit and this application's NGINX locations file.

Upgrading from a version that installed a stand-alone site: the playbook removes the old `/etc/nginx/sites-*/stardash` site, which would otherwise take over the whole server. The old `/opt/bi-dashboard` folder is left in place; delete it once the new deployment works. TLS is not configured by the playbook; add it with certbot as described in Option C.

## Using the dashboard

1. Log in as a member of the admin role and click **New dashboard**. Choose the view, enter a name, and select the roles allowed to read it.
2. Open the dashboard and add widgets:
   - **+ KPI:** pick a measure.
   - **+ Chart:** choose the chart type first, then the x-axis field (the main date is listed once for each of day, week, month, quarter and year), an optional breakdown, and one or more measures. With several measures you get one series per measure, or per measure and breakdown value. Stacked bars stack each measure separately. If you mix € and non-€ measures, the non-€ ones use a second axis on the right. Pie and doughnut charts take one measure and no breakdown. Use ⇤⇥ to switch between half and full width.
   - **+ Table:** pick the group-by columns and the measures. The ⤓ button in the table header downloads the rows shown (up to 1000, with the current filters applied), with measures as plain numbers.
3. Use the filter bar. Choosing a **Period** fills in the start and end dates and applies them immediately, and KPIs then show the % change from the previous period. Typing your own dates switches the period to "Custom", which shows values without a % change. Click **Apply** after changing dates or attribute filters.
4. Click **Export** to download the dashboard as PDF or Word. The PDF is A4 landscape and keeps the dashboard layout: KPI cards across the top, half-width charts side by side, and page numbers in the footer. Tables longer than 500 rows are cut off with a note.

Widgets are saved to the dashboard. Any user who can open a dashboard can add, edit or remove its widgets. Only admins can create or delete dashboards.

## Offline servers

Chart.js 4.4.1 is loaded from cdn.jsdelivr.net. If the server or users have no internet access, download it into the app and point the template at the local copy:

```bash
curl -L -o app/static/js/chart.umd.min.js https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js
```

Then in `app/templates/dashboard.html`, replace the CDN `<script>` tag with:

```html
<script src="{{ url_for('static', filename='js/chart.umd.min.js') }}"></script>
```

## Tests

```bash
venv/bin/pytest
```

The unit tests cover period calculations, column classification, SQL generation and chart data shaping. They do not need a database.

## Checking the query log

```sql
SELECT start_time, duration_seconds, activity_description, "user", dashboard_name
FROM bi_config.query_log ORDER BY start_time DESC LIMIT 50;
```
