import os


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///app.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload settings
    UPLOAD_FOLDER = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "storage"
    )
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500 MB
    ALLOWED_EXTENSIONS = {
        "mp3", "wav", "ogg", "flac", "aac",   # audio
        "mp4", "avi", "mkv", "mov", "webm",    # video
    }


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False

    # Security hardening
    SESSION_COOKIE_SECURE = True        # cookies only over HTTPS
    SESSION_COOKIE_HTTPONLY = True       # no JS access to session cookie
    SESSION_COOKIE_SAMESITE = "Lax"     # CSRF mitigation
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True

    # Trust proxy headers from Nginx
    PREFERRED_URL_SCHEME = "https"
