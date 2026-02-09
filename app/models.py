"""Database models – User and MediaFile."""

from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, login_manager


class User(UserMixin, db.Model):
    """User account (Admin or Standard)."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")  # "admin" | "user"
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    files = db.relationship("MediaFile", backref="owner", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


class MediaFile(db.Model):
    """An uploaded (and encrypted) media file."""
    __tablename__ = "media_files"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False, unique=True)
    file_size = db.Column(db.Integer, default=0)
    mime_type = db.Column(db.String(100))
    status = db.Column(db.String(20), default="encrypted")  # encrypted | deleted
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Encryption metadata (Fernet-wrapped AES key stored as text)
    encrypted_key = db.Column(db.Text, nullable=True)

    def __repr__(self) -> str:
        return f"<MediaFile {self.original_filename} ({self.status})>"


class AuditLog(db.Model):
    """Audit trail for every significant action."""
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    media_id = db.Column(db.Integer, db.ForeignKey("media_files.id"), nullable=True)
    result = db.Column(db.String(20), default="success")
    detail = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} user={self.user_id}>"


# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return db.session.get(User, int(user_id))
