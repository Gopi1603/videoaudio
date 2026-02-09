"""Application factory – creates and configures the Flask app."""

import os
from flask import Flask, render_template, jsonify, request
from sqlalchemy import text
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"
csrf = CSRFProtect()


def create_app(config_name: str = "config.DevelopmentConfig") -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_name)

    # Ensure storage directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Initialise extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Import models so SQLAlchemy knows about them
    from app.models import User, MediaFile, AuditLog  # noqa: F401
    from app.kms import KeyRecord, KeyShare  # noqa: F401
    from app.policy import Policy, PolicyLog  # noqa: F401

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.media.routes import media_bp
    from app.admin.routes import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(admin_bp)

    # ----- Error handlers -----
    @app.errorhandler(404)
    def not_found(e):
        if request.accept_mimetypes.accept_json and \
           not request.accept_mimetypes.accept_html:
            return jsonify({"error": "Not found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        if request.accept_mimetypes.accept_json and \
           not request.accept_mimetypes.accept_html:
            return jsonify({"error": "Forbidden"}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def server_error(e):
        if request.accept_mimetypes.accept_json and \
           not request.accept_mimetypes.accept_html:
            return jsonify({"error": "Internal server error"}), 500
        return render_template("errors/500.html"), 500

    # Create tables on first request (dev convenience)
    with app.app_context():
        db.create_all()

    # ----- Health check endpoint (used by Docker / load balancers) -----
    @app.route("/health")
    def health_check():
        """Lightweight health probe — returns 200 if app is alive."""
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify({"status": "healthy", "db": "ok"}), 200
        except Exception as e:
            return jsonify({"status": "unhealthy", "db": str(e)}), 503

    return app
