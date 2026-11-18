"""HTML pages: login, dashboard list and dashboard screen."""
from flask import Blueprint, render_template, request, redirect, url_for, session, abort, flash

from app import auth, repository

bp = Blueprint("views", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username and auth.verify_credentials(username, password):
            auth.login_user(username, auth.lookup_roles(username))
            # "next" is a path inside this application (without the URL prefix)
            target = request.args.get("next", "")
            if not target.startswith("/") or target.startswith("//") or "\\" in target:
                return redirect(url_for("views.dashboard_list"))
            return redirect(request.script_root + target)
        flash("Invalid username or password")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("views.login"))


@bp.route("/")
@auth.login_required
def dashboard_list():
    dashboards = [d for d in repository.list_dashboards() if auth.can_access(d["roles"])]
    return render_template("dashboard_list.html", dashboards=dashboards, is_admin=auth.is_admin())


@bp.route("/dashboard/<int:dashboard_id>")
@auth.login_required
def dashboard(dashboard_id):
    dash = repository.get_dashboard(dashboard_id)
    if not dash:
        abort(404)
    if not auth.can_access(dash["roles"]):
        abort(403)
    return render_template("dashboard.html", dashboard=dash)
