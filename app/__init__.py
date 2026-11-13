"""BI Dashboard Flask application."""
import logging

from flask import Flask, jsonify, request, render_template

import config


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # export payloads carry chart images

    logging.basicConfig(level=logging.INFO)

    from app.routes.views import bp as views_bp
    from app.routes.api import bp as api_bp
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

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

    return app
