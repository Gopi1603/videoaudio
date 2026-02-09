"""Tests for auth & media routes (Flask test client)."""

import os
import pytest

os.environ["FERNET_MASTER_KEY"] = "t2JVH7Bj3GkX6vN8QfW0MpYrA5z1LcDs9iUoEhKlRxw="

from app import create_app, db
from app.models import User


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
              password="Testpass1!", confirm="Testpass1!"):
    return client.post("/auth/register", data={
        "username": username, "email": email,
        "password": password, "confirm_password": confirm,
    }, follow_redirects=True)


def _login(client, email="test@example.com", password="Testpass1!"):
    return client.post("/auth/login", data={
        "email": email, "password": password,
    }, follow_redirects=True)


class TestAuth:
    def test_register_success(self, client):
        rv = _register(client)
        assert rv.status_code == 200
        assert b"Registration successful" in rv.data

    def test_duplicate_email(self, client):
        _register(client)
        rv = _register(client, username="other")
        assert b"Email already registered" in rv.data

    def test_login_success(self, client):
        _register(client)
        rv = _login(client)
        assert rv.status_code == 200
        assert b"Dashboard" in rv.data or b"My Encrypted Files" in rv.data

    def test_login_wrong_password(self, client):
        _register(client)
        rv = _login(client, password="wrong")
        assert b"Invalid email or password" in rv.data

    def test_logout(self, client):
        _register(client)
        _login(client)
        rv = client.get("/auth/logout", follow_redirects=True)
        assert b"logged out" in rv.data.lower()


class TestMediaUploadDownload:
    def test_upload_requires_login(self, client):
        rv = client.get("/upload", follow_redirects=True)
        assert b"Log In" in rv.data

    def test_upload_and_download(self, client, app):
        _register(client)
        _login(client)

        import io
        data = {
            "file": (io.BytesIO(b"\x00" * 1024), "test.mp3"),
        }
        rv = client.post("/upload", data=data,
                         content_type="multipart/form-data",
                         follow_redirects=True)
        assert b"encrypted" in rv.data.lower() or b"stored successfully" in rv.data.lower()

        # Download
        from app.models import MediaFile
        with app.app_context():
            mf = MediaFile.query.first()
            assert mf is not None
            rv = client.get(f"/download/{mf.id}")
            assert rv.status_code == 200
            assert rv.data == b"\x00" * 1024

    def test_delete_file(self, client, app):
        _register(client)
        _login(client)

        import io
        client.post("/upload", data={
            "file": (io.BytesIO(b"data"), "test.wav"),
        }, content_type="multipart/form-data", follow_redirects=True)

        from app.models import MediaFile
        with app.app_context():
            mf = MediaFile.query.first()
            rv = client.post(f"/delete/{mf.id}", follow_redirects=True)
            assert b"deleted" in rv.data.lower()
