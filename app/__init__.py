"""Application factory – creates and configures the Flask app."""

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"


def create_app(config_name: str = "config.DevelopmentConfig") -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_name)

    # Ensure storage directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Initialise extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Import models so SQLAlchemy knows about them
    from app.models import User  # noqa: F401

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.media.routes import media_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(media_bp)

    # Create tables on first request (dev convenience)
    with app.app_context():
        db.create_all()

    return app
