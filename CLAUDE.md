# BI Dashboard
Web based Dashboard for Business Intelligence analysis.

## Dashboard Front End Design
There are 2 screens

### 1. Dashboard List
A screen that presents users with:
-  a list of available dashboards: selecting a Dashboard opens up the Dashboard screen. Beside each dashboard is a delete dashboard button to remove the dashboard from the application repository
 - the option to add a new dashboard: this brings up a dialogue asking users for the view, dashboard name and what roles are allow to read the dashboard.

### 2. Dashboard 
Screen showing a Dashboard. This should include filters across the top allowing the user to select a subset of the available dataset, and the ability to add charts, KPIs and tables to the Dashboard.
When a chart is added, there is a dialogue that asks what chart type.
For date there should be start and end dates, and a period, that provides a shortcut for populating start and end date.
If a period is selected then KPIs should show the percentage change from the previous period.
For charts there should be a control that toggles between full screen and half screen width.
Charts should include:
- x axis field. This should include time subdivisions day, week, month, quarter, year for the main date
- breakdown 
- one or more measures
- type
Tables should contain an export to csv button
A button that allows the dashboard to be exported as either pdf or word

## additional functional requirements
Application should maintain the list of available dashboards from a configuration database table.

Each dashboard takes data from a single view, treating columns starting with 
 - euro_ as facts containing euro values
 - ms_ as additive measures
 - date_ as the main date attribute
 - all other columns as attributes

 All database queries are logged to a repository table with columns for start_time, end_time, duration_seconds, activity description, user, dashboard_name

## Security Requirements
Database roles are used to control access.
Only users with a special admin role should be allowed to create and delete dashboards - this role name should be in the config file. This role also has read access to all dashboards.
Each dashboard is associated with one or more database roles - only these roles can access the dashboard, and see it in the dashboard list.

## Technical stack
1. Designed to run on Ubuntu
2. Connects to PostgreSQL using the credentials in the config file config.py
3. uses python flask
4. Uses NGINX as a web server
5. Uses gunicorn as WSGI


## Database Design
Application configuration should be stored in a schema indicated in the config file. Source views for dashboard data can be anywhere on the same database.

## Technical instructions
Don't start the app automatically. Create a readme file that includes startup instructions. Include code for deployment via Ansible.
Do not perform any git actions.