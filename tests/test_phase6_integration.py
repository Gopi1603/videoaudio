"""
Phase 6 — Testing & Validation: Integration, Policy Penetration, E2E
Multi-role integration tests, policy bypass attempts, concurrent simulation.
"""

import io
import os
import json
import time
import pytest

os.environ["FERNET_MASTER_KEY"] = "t2JVH7Bj3GkX6vN8QfW0MpYrA5z1LcDs9iUoEhKlRxw="

from app import create_app, db
from app.models import User, MediaFile, AuditLog
from app.kms import store_key, retrieve_key, revoke_key, generate_file_key
from app.policy import create_policy, PolicyType, check_access


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


def _register(client, username="testuser1", email="user1@test.com", password="Testpass1!"):
    return client.post("/auth/register", data={
        "username": username, "email": email,
        "password": password, "confirm_password": password,
    }, follow_redirects=True)


def _login(client, email="user1@test.com", password="Testpass1!"):
    return client.post("/auth/login", data={
        "email": email, "password": password,
    }, follow_redirects=True)


def _make_admin(app, email="u1@test.com"):
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        u.role = "admin"
        db.session.commit()


def _upload(client, name="test.mp3", data=b"\x00" * 1024):
    return client.post("/upload", data={
        "file": (io.BytesIO(data), name),
    }, content_type="multipart/form-data", follow_redirects=True)


# ── E2E Integration: Full Upload → Download → Delete ──────────────────

class TestE2EIntegration:
    def test_full_lifecycle(self, client, app):
        """Upload → view detail → download → delete for one user."""
        _register(client)
        _login(client)
        _upload(client, "lifecycle.wav", os.urandom(512))

        with app.app_context():
            mf = MediaFile.query.first()
            fid = mf.id

        # File detail
        rv = client.get(f"/file/{fid}")
        assert rv.status_code == 200
        assert b"lifecycle.wav" in rv.data

        # Download
        rv = client.get(f"/download/{fid}")
        assert rv.status_code == 200

        # Delete
        rv = client.post(f"/delete/{fid}", follow_redirects=True)
        assert b"deleted" in rv.data.lower()

        # Verify deleted
        with app.app_context():
            mf = db.session.get(MediaFile, fid)
            assert mf.status == "deleted"

    def test_multi_user_isolation(self, client, app):
        """User A's files are NOT visible/downloadable by User B."""
        # User A uploads
        _register(client, "alice", "alice@test.com")
        _login(client, "alice@test.com")
        _upload(client, "alice_file.mp3")
        client.get("/auth/logout")

        with app.app_context():
            fid = MediaFile.query.first().id

        # User B tries to access
        _register(client, "bob", "bob@test.com")
        _login(client, "bob@test.com")

        rv = client.get(f"/file/{fid}")
        assert rv.status_code == 403

        rv = client.get(f"/download/{fid}")
        # Policy should deny non-owner
        assert rv.status_code in (302, 403)

    def test_admin_can_access_any_file(self, client, app):
        """Admin can view and download any user's files."""
        _register(client, "uploader", "uploader@test.com")
        _login(client, "uploader@test.com")
        _upload(client, "shared.mp3")
        client.get("/auth/logout")

        _register(client, "adminuser", "admin@test.com")
        _make_admin(app, "admin@test.com")
        _login(client, "admin@test.com")

        with app.app_context():
            fid = MediaFile.query.first().id

        # Admin sees file detail
        rv = client.get(f"/file/{fid}")
        assert rv.status_code == 200

        # Admin can download (policy allows admin)
        rv = client.get(f"/download/{fid}")
        assert rv.status_code == 200

    def test_multiple_uploads_same_user(self, client, app):
        """User can upload multiple files and see all on dashboard."""
        _register(client)
        _login(client)
        for i in range(5):
            _upload(client, f"file_{i}.wav", os.urandom(128))

        rv = client.get("/")
        assert rv.status_code == 200
        with app.app_context():
            count = MediaFile.query.filter_by(status="encrypted").count()
            assert count == 5

        # API also returns 5
        rv = client.get("/api/files")
        data = json.loads(rv.data)
        assert len(data) == 5


# ── Policy Penetration Testing ────────────────────────────────────────

class TestPolicyPenetration:
    """Phase 6: Try to bypass policies by manipulating API calls."""

    def test_regular_user_cannot_hit_admin_api(self, client, app):
        _register(client)
        _login(client)
        rv = client.get("/admin/api/keys")
        assert rv.status_code in (302, 403)

    def test_regular_user_cannot_toggle_admin(self, client, app):
        _register(client)
        _login(client)
        rv = client.post("/admin/users/1/toggle-admin", follow_redirects=True)
        # admin_required flashes and redirects to dashboard
        assert rv.status_code == 200
        assert b"Admin access required" in rv.data or b"Dashboard" in rv.data

    def test_regular_user_cannot_revoke_key(self, client, app):
        _register(client)
        _login(client)
        rv = client.post("/admin/keys/1/revoke", follow_redirects=True)
        assert rv.status_code == 200
        assert b"Admin access required" in rv.data or b"Dashboard" in rv.data

    def test_regular_user_cannot_create_policy(self, client, app):
        _register(client)
        _login(client)
        rv = client.post("/admin/policies/create", data={
            "media_id": 1, "policy_type": "admin_override",
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert b"Admin access required" in rv.data or b"Dashboard" in rv.data

    def test_unauthenticated_access_redirects(self, client, app):
        """Protected routes redirect unauthenticated users to login."""
        protected = ["/upload", "/profile", "/admin/files",
                     "/admin/keys", "/admin/users", "/admin/policies",
                     "/admin/audit", "/api/files"]
        for url in protected:
            rv = client.get(url)
            assert rv.status_code in (302, 401), f"{url} accessible without login"

    def test_unauthenticated_home_is_public(self, client, app):
        rv = client.get("/")
        assert rv.status_code == 200

    def test_delete_others_file_rejected(self, client, app):
        """User cannot delete another user's file via POST."""
        _register(client, "owner", "owner@test.com")
        _login(client, "owner@test.com")
        _upload(client, "secret.mp3")
        client.get("/auth/logout")

        with app.app_context():
            fid = MediaFile.query.first().id

        _register(client, "attacker", "attacker@test.com")
        _login(client, "attacker@test.com")

        rv = client.post(f"/delete/{fid}")
        assert rv.status_code == 403

    def test_api_delete_others_file_rejected(self, client, app):
        """API DELETE on another user's file returns 403."""
        _register(client, "owner", "owner@test.com")
        _login(client, "owner@test.com")
        _upload(client, "secret.mp3")
        client.get("/auth/logout")

        with app.app_context():
            fid = MediaFile.query.first().id

        _register(client, "attacker", "attacker@test.com")
        _login(client, "attacker@test.com")

        rv = client.delete(f"/api/files/{fid}")
        assert rv.status_code == 403

    def test_key_revocation_prevents_decryption(self, app):
        """Phase 6: Key revocation renders file undecryptable."""
        with app.app_context():
            u = User(username="ktest", email="ktest@test.com", role="user")
            u.set_password("Testpass1!")
            db.session.add(u)
            db.session.commit()

            mf = MediaFile(
                owner_id=u.id, original_filename="k.mp3",
                stored_filename="k.mp3.enc", file_size=100,
                mime_type="audio/mpeg", status="encrypted",
            )
            db.session.add(mf)
            db.session.commit()

            key = generate_file_key()
            store_key(mf.id, key)
            assert retrieve_key(mf.id) == key

            revoke_key(mf.id)
            assert retrieve_key(mf.id) is None, "Key still retrievable after revocation"


# ── Audit Logging ─────────────────────────────────────────────────────

class TestAuditTrail:
    def test_login_creates_audit_log(self, client, app):
        _register(client)
        _login(client)
        with app.app_context():
            log = AuditLog.query.filter_by(action="login").first()
            assert log is not None
            assert log.result == "success"

    def test_failed_login_logged(self, client, app):
        _register(client)
        _login(client, password="wrongpassword")
        with app.app_context():
            log = AuditLog.query.filter_by(action="login", result="failure").first()
            assert log is not None

    def test_upload_creates_audit_log(self, client, app):
        _register(client)
        _login(client)
        _upload(client)
        with app.app_context():
            log = AuditLog.query.filter_by(action="upload").first()
            assert log is not None
            assert log.result == "success"
            assert log.media_id is not None

    def test_download_creates_audit_log(self, client, app):
        _register(client)
        _login(client)
        _upload(client)
        with app.app_context():
            fid = MediaFile.query.first().id
        client.get(f"/download/{fid}")
        with app.app_context():
            log = AuditLog.query.filter_by(action="download").first()
            assert log is not None

    def test_delete_creates_audit_log(self, client, app):
        _register(client)
        _login(client)
        _upload(client)
        with app.app_context():
            fid = MediaFile.query.first().id
        client.post(f"/delete/{fid}")
        with app.app_context():
            log = AuditLog.query.filter_by(action="delete").first()
            assert log is not None
            assert log.result == "success"

    def test_register_creates_audit_log(self, client, app):
        _register(client)
        with app.app_context():
            log = AuditLog.query.filter_by(action="register").first()
            assert log is not None


# ── Performance: Route Response Times ─────────────────────────────────

class TestRoutePerformance:
    def test_dashboard_response_time(self, client, app):
        _register(client)
        _login(client)
        # Upload a few files
        for i in range(3):
            _upload(client, f"perf_{i}.wav", os.urandom(256))

        t0 = time.perf_counter()
        rv = client.get("/")
        elapsed = time.perf_counter() - t0
        print(f"  Dashboard response: {elapsed*1000:.0f}ms")
        assert rv.status_code == 200
        assert elapsed < 2.0, f"Dashboard too slow: {elapsed:.2f}s"

    def test_api_files_response_time(self, client, app):
        _register(client)
        _login(client)
        for i in range(5):
            _upload(client, f"api_perf_{i}.wav", os.urandom(128))

        t0 = time.perf_counter()
        rv = client.get("/api/files")
        elapsed = time.perf_counter() - t0
        print(f"  API /api/files response: {elapsed*1000:.0f}ms")
        assert rv.status_code == 200
        assert elapsed < 1.0

    def test_upload_response_time_small_file(self, client, app):
        _register(client)
        _login(client)
        t0 = time.perf_counter()
        _upload(client, "perf.wav", os.urandom(1024))
        elapsed = time.perf_counter() - t0
        print(f"  Upload 1KB response: {elapsed*1000:.0f}ms")
        assert elapsed < 10.0
