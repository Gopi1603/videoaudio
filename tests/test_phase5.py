"""Phase 5 tests — Frontend pages, REST API, error handlers, profile, file detail."""

import io
import os
import json
import pytest

os.environ["FERNET_MASTER_KEY"] = "t2JVH7Bj3GkX6vN8QfW0MpYrA5z1LcDs9iUoEhKlRxw="

from app import create_app, db
from app.models import User, MediaFile


# ── Fixtures ───────────────────────────────────────────────────────────
@pytest.fixture()
def app():
    application = create_app("config.TestingConfig")
    with application.app_context():
        db.create_all()
        yield application
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _register(client, username="testuser", email="test@example.com",
              password="Testpass1!"):
    return client.post("/auth/register", data={
        "username": username, "email": email,
        "password": password, "confirm_password": password,
    }, follow_redirects=True)


def _login(client, email="test@example.com", password="Testpass1!"):
    return client.post("/auth/login", data={
        "email": email, "password": password,
    }, follow_redirects=True)


def _make_admin(app, email="test@example.com"):
    """Promote user to admin."""
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        u.role = "admin"
        db.session.commit()


def _upload_file(client, name="test.mp3", content=b"\x00" * 1024):
    return client.post("/upload", data={
        "file": (io.BytesIO(content), name),
    }, content_type="multipart/form-data", follow_redirects=True)


# ── Profile Page ───────────────────────────────────────────────────────
class TestProfilePage:
    def test_profile_requires_login(self, client):
        rv = client.get("/profile", follow_redirects=True)
        assert b"Log In" in rv.data

    def test_profile_renders(self, client):
        _register(client)
        _login(client)
        rv = client.get("/profile")
        assert rv.status_code == 200
        assert b"testuser" in rv.data
        assert b"test@example.com" in rv.data
        assert b"Recent Activity" in rv.data

    def test_profile_shows_stats(self, client, app):
        _register(client)
        _login(client)
        _upload_file(client)
        rv = client.get("/profile")
        assert rv.status_code == 200
        assert b"My Files" in rv.data


# ── File Detail Page ───────────────────────────────────────────────────
class TestFileDetailPage:
    def test_file_detail_requires_login(self, client, app):
        rv = client.get("/file/1", follow_redirects=True)
        assert b"Log In" in rv.data

    def test_file_detail_renders(self, client, app):
        _register(client)
        _login(client)
        _upload_file(client)
        with app.app_context():
            mf = MediaFile.query.first()
            rv = client.get(f"/file/{mf.id}")
            assert rv.status_code == 200
            assert b"test.mp3" in rv.data
            assert b"Watermark Info" in rv.data
            assert b"AES-256-GCM" in rv.data

    def test_file_detail_404(self, client):
        _register(client)
        _login(client)
        rv = client.get("/file/9999")
        assert rv.status_code == 404

    def test_file_detail_forbidden_for_other_user(self, client, app):
        _register(client, username="user1", email="u1@test.com")
        _login(client, email="u1@test.com")
        _upload_file(client)
        client.get("/auth/logout")

        _register(client, username="user2", email="u2@test.com")
        _login(client, email="u2@test.com")
        with app.app_context():
            mf = MediaFile.query.first()
            rv = client.get(f"/file/{mf.id}")
            assert rv.status_code == 403


# ── REST API — File Listing ────────────────────────────────────────────
class TestRESTAPI:
    def test_api_files_requires_login(self, client):
        rv = client.get("/api/files")
        assert rv.status_code in (302, 401)

    def test_api_files_returns_json(self, client, app):
        _register(client)
        _login(client)
        _upload_file(client)
        rv = client.get("/api/files")
        assert rv.status_code == 200
        data = json.loads(rv.data)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["filename"] == "test.mp3"

    def test_api_file_detail(self, client, app):
        _register(client)
        _login(client)
        _upload_file(client)
        with app.app_context():
            mf = MediaFile.query.first()
            rv = client.get(f"/api/files/{mf.id}")
            assert rv.status_code == 200
            data = json.loads(rv.data)
            assert data["filename"] == "test.mp3"
            assert "watermark_id" in data

    def test_api_file_detail_404(self, client):
        _register(client)
        _login(client)
        rv = client.get("/api/files/9999")
        assert rv.status_code == 404

    def test_api_delete_file(self, client, app):
        _register(client)
        _login(client)
        _upload_file(client)
        with app.app_context():
            mf = MediaFile.query.first()
            rv = client.delete(f"/api/files/{mf.id}")
            assert rv.status_code == 200
            data = json.loads(rv.data)
            assert data["message"] == "File deleted"

    def test_api_upload(self, client, app):
        _register(client)
        _login(client)
        rv = client.post("/api/upload", data={
            "file": (io.BytesIO(b"\x00" * 512), "api_test.wav"),
        }, content_type="multipart/form-data")
        assert rv.status_code == 201
        data = json.loads(rv.data)
        assert data["filename"] == "api_test.wav"
        assert "id" in data

    def test_api_upload_no_file(self, client):
        _register(client)
        _login(client)
        rv = client.post("/api/upload", data={}, content_type="multipart/form-data")
        assert rv.status_code == 400

    def test_api_upload_bad_extension(self, client):
        _register(client)
        _login(client)
        rv = client.post("/api/upload", data={
            "file": (io.BytesIO(b"data"), "test.exe"),
        }, content_type="multipart/form-data")
        assert rv.status_code == 400


# ── Error Pages ────────────────────────────────────────────────────────
class TestErrorPages:
    def test_404_page(self, client):
        _register(client)
        _login(client)
        rv = client.get("/nonexistent-page-xyz")
        assert rv.status_code == 404
        assert b"404" in rv.data
        assert b"Page Not Found" in rv.data

    def test_403_page(self, client, app):
        """Non-admin accessing admin route gets 403."""
        _register(client)
        _login(client)
        rv = client.get("/admin/files")
        assert rv.status_code == 403
        assert b"403" in rv.data or b"Access Denied" in rv.data


# ── Dashboard Stats ────────────────────────────────────────────────────
class TestDashboardUI:
    def test_dashboard_empty(self, client):
        _register(client)
        _login(client)
        rv = client.get("/")
        assert rv.status_code == 200
        assert b"No files yet" in rv.data

    def test_dashboard_with_files(self, client, app):
        _register(client)
        _login(client)
        _upload_file(client)
        rv = client.get("/")
        assert rv.status_code == 200
        assert b"test.mp3" in rv.data
        assert b"Total Files" in rv.data

    def test_upload_page_renders(self, client):
        _register(client)
        _login(client)
        rv = client.get("/upload")
        assert rv.status_code == 200
        assert b"Drag" in rv.data
        assert b"Encrypt" in rv.data


# ── Admin Restrictions ─────────────────────────────────────────────────
class TestAdminRestrictions:
    def test_non_admin_cannot_see_keys(self, client):
        _register(client)
        _login(client)
        rv = client.get("/admin/keys", follow_redirects=True)
        assert b"Admin access required" in rv.data

    def test_non_admin_cannot_see_users(self, client):
        _register(client)
        _login(client)
        rv = client.get("/admin/users", follow_redirects=True)
        assert b"Admin access required" in rv.data

    def test_non_admin_cannot_see_policies(self, client):
        _register(client)
        _login(client)
        rv = client.get("/admin/policies", follow_redirects=True)
        assert b"Admin access required" in rv.data

    def test_non_admin_cannot_see_audit(self, client):
        _register(client)
        _login(client)
        rv = client.get("/admin/audit", follow_redirects=True)
        assert b"Admin access required" in rv.data

    def test_admin_can_access_keys(self, client, app):
        _register(client)
        _make_admin(app)
        _login(client)
        rv = client.get("/admin/keys")
        assert rv.status_code == 200
        assert b"Key Management" in rv.data

    def test_admin_can_access_users(self, client, app):
        _register(client)
        _make_admin(app)
        _login(client)
        rv = client.get("/admin/users")
        assert rv.status_code == 200
        assert b"User Management" in rv.data

    def test_admin_can_access_all_files(self, client, app):
        _register(client)
        _make_admin(app)
        _login(client)
        rv = client.get("/admin/files")
        assert rv.status_code == 200
        assert b"All Files" in rv.data
