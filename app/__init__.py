"""BI Dashboard Flask application."""
import logging

from flask import Flask, jsonify, request, render_template, redirect

import config


def normalise_prefix(prefix):
    """'stardash', '/stardash/' -> '/stardash'; '' or '/' -> ''."""
    prefix = (prefix or "").strip().strip("/")
    return "/" + prefix if prefix else ""


class PrefixMiddleware:
    """Serve the application under a URL prefix such as /stardash.

    NGINX forwards the full path (/stardash/dashboard/1). This moves the prefix
    from PATH_INFO into SCRIPT_NAME, so the routes stay unprefixed while
    url_for() generates prefixed URLs for pages, static files and redirects.
    The development server works the same way: http://127.0.0.1:5000/stardash/.
    """

    def __init__(self, wsgi_app, prefix):
        self.wsgi_app = wsgi_app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == self.prefix or path.startswith(self.prefix + "/"):
            environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "").rstrip("/") + self.prefix
            environ["PATH_INFO"] = path[len(self.prefix):] or "/"
            return self.wsgi_app(environ, start_response)
        if path in ("", "/"):
            # Convenience when running without NGINX: / -> /stardash/
            return redirect(self.prefix + "/")(environ, start_response)
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return [b"Not found"]


def create_app():
    app = Flask(__name__)
    prefix = normalise_prefix(getattr(config, "URL_PREFIX", ""))

    app.config["SECRET_KEY"] = config.SECRET_KEY
    # Several applications share the host name: give this one its own cookie,
    # scoped to its own path, so logging in to one does not log out the others.
    app.config["SESSION_COOKIE_NAME"] = (prefix.strip("/").replace("/", "_") or "bi_dashboard") + "_session"
    app.config["SESSION_COOKIE_PATH"] = prefix + "/" if prefix else "/"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # export payloads carry chart images

    logging.basicConfig(level=logging.INFO)

    from app.routes.views import bp as views_bp
    from app.routes.api import bp as api_bp
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    # request.path below is relative to the prefix (e.g. /api/...), so these checks need no prefix.
    @app.errorhandler(403)
    def forbidden(_):
        if request.path.startswith("/api/"):
            return jsonify(error="Forbidden"), 403
        return render_template("error.html", message="You do not have access to this page."), 403

    @app.errorhandler(404)
    def not_found(_):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found"), 404
        return render_template("error.html", message="Page not found."), 404

    if prefix:
        app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix)
    return app
