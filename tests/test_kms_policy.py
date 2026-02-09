"""Tests for Phase 4: Key Management Service (KMS) and Policy Engine."""

import os
import pytest
from datetime import datetime, timezone, timedelta

os.environ["FERNET_MASTER_KEY"] = "t2JVH7Bj3GkX6vN8QfW0MpYrA5z1LcDs9iUoEhKlRxw="

from app import create_app, db
from app.models import User, MediaFile
from app.kms import (
    split_secret, reconstruct_secret, generate_file_key,
    wrap_key, unwrap_key, store_key, retrieve_key, revoke_key,
    get_key_info, KeyRecord, KeyShare
)
from app.policy import (
    PolicyType, AccessDecision, PolicyContext, evaluate_policy,
    check_access, create_policy, Policy, share_file
)


@pytest.fixture
def app():
    """Create test application."""
    app = create_app("config.TestingConfig")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def setup_users(app):
    """Create test users."""
    with app.app_context():
        # Admin may already exist from auto-create in create_app()
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(username="admin", email="admin@test.com", role="admin")
            admin.set_password("adminpass")
            db.session.add(admin)
        else:
            admin.email = "admin@test.com"
            admin.set_password("adminpass")
        user1 = User(username="user1", email="user1@test.com", role="user")
        user1.set_password("user1pass")
        user2 = User(username="user2", email="user2@test.com", role="user")
        user2.set_password("user2pass")
        db.session.add_all([user1, user2])
        db.session.commit()
        return {"admin": admin.id, "user1": user1.id, "user2": user2.id}


@pytest.fixture
def setup_file(app, setup_users):
    """Create a test media file."""
    with app.app_context():
        media = MediaFile(
            owner_id=setup_users["user1"],
            original_filename="test.mp3",
            stored_filename="test123.mp3.enc",
            file_size=1000,
            mime_type="audio/mpeg",
            status="encrypted"
        )
        db.session.add(media)
        db.session.commit()
        return media.id


# ---------------------------------------------------------------------------
# Shamir's Secret Sharing Tests
# ---------------------------------------------------------------------------
class TestShamirSecretSharing:
    def test_split_and_reconstruct(self):
        """Test basic split and reconstruct with threshold shares."""
        secret = b"my_secret_key_32_bytes_exactly!!"  # 32 bytes
        shares = split_secret(secret, n=5, k=3)
        
        assert len(shares) == 5
        # Each share is 2 bytes per secret byte (to handle values 0-256)
        assert all(len(s[1]) == len(secret) * 2 for s in shares)
        
        # Reconstruct with exactly threshold shares
        reconstructed = reconstruct_secret(shares[:3], len(secret))
        assert reconstructed == secret
    
    def test_reconstruct_with_any_k_shares(self):
        """Any k shares should reconstruct the secret."""
        secret = b"another_secret_32_bytes_here!!!"
        shares = split_secret(secret, n=5, k=3)
        
        # Use different combinations
        assert reconstruct_secret([shares[0], shares[2], shares[4]], len(secret)) == secret
        assert reconstruct_secret([shares[1], shares[3], shares[4]], len(secret)) == secret
        assert reconstruct_secret(shares[2:5], len(secret)) == secret
    
    def test_reconstruct_with_more_than_k_shares(self):
        """More than k shares should still work."""
        secret = b"32_byte_secret_for_testing_!!!"
        shares = split_secret(secret, n=5, k=3)
        
        # Use all 5 shares
        reconstructed = reconstruct_secret(shares, len(secret))
        assert reconstructed == secret
    
    def test_invalid_threshold(self):
        """Threshold cannot exceed total shares."""
        with pytest.raises(ValueError):
            split_secret(b"secret", n=3, k=5)
    
    def test_minimum_threshold(self):
        """Threshold must be at least 2."""
        with pytest.raises(ValueError):
            split_secret(b"secret", n=3, k=1)


# ---------------------------------------------------------------------------
# KMS Key Storage Tests
# ---------------------------------------------------------------------------
class TestKMS:
    def test_wrap_unwrap_roundtrip(self, app):
        """Test key wrapping and unwrapping."""
        with app.app_context():
            key = generate_file_key()
            wrapped = wrap_key(key)
            unwrapped = unwrap_key(wrapped)
            assert unwrapped == key
    
    def test_store_simple_key(self, app, setup_file):
        """Test storing a key without splitting."""
        with app.app_context():
            key = generate_file_key()
            record = store_key(setup_file, key, n_shares=1, threshold=1)
            
            assert record.media_id == setup_file
            assert record.total_shares == 1
            assert record.threshold == 1
            assert record.status == "active"
            assert record.encrypted_key is not None
    
    def test_store_split_key(self, app, setup_file):
        """Test storing a key with Shamir's splitting."""
        with app.app_context():
            key = generate_file_key()
            record = store_key(setup_file, key, n_shares=3, threshold=2)
            
            assert record.total_shares == 3
            assert record.threshold == 2
            assert record.encrypted_key is None  # Key is split, not stored directly
            
            shares = KeyShare.query.filter_by(key_record_id=record.id).all()
            assert len(shares) == 3
    
    def test_retrieve_simple_key(self, app, setup_file):
        """Test retrieving a non-split key."""
        with app.app_context():
            key = generate_file_key()
            store_key(setup_file, key, n_shares=1)
            
            retrieved = retrieve_key(setup_file)
            assert retrieved == key
    
    def test_retrieve_split_key_auto(self, app, setup_file):
        """Test auto-retrieval of split key (admin use)."""
        with app.app_context():
            key = generate_file_key()
            store_key(setup_file, key, n_shares=3, threshold=2)
            
            # Auto-retrieve should work for admin
            retrieved = retrieve_key(setup_file)
            assert retrieved == key
    
    def test_revoke_key(self, app, setup_file):
        """Test key revocation."""
        with app.app_context():
            key = generate_file_key()
            store_key(setup_file, key)
            
            success = revoke_key(setup_file)
            assert success
            
            record = KeyRecord.query.filter_by(media_id=setup_file).first()
            assert record.status == "revoked"
            
            # Should not be able to retrieve revoked key
            retrieved = retrieve_key(setup_file)
            assert retrieved is None
    
    def test_get_key_info(self, app, setup_file):
        """Test getting key metadata."""
        with app.app_context():
            key = generate_file_key()
            store_key(setup_file, key, n_shares=3, threshold=2)
            
            info = get_key_info(setup_file)
            assert info["media_id"] == setup_file
            assert info["total_shares"] == 3
            assert info["threshold"] == 2
            assert info["status"] == "active"
            assert len(info["shares"]) == 3


# ---------------------------------------------------------------------------
# Policy Engine Tests
# ---------------------------------------------------------------------------
class TestPolicyEngine:
    def test_admin_always_allowed(self, app, setup_users, setup_file):
        """Admins should have access to any file."""
        with app.app_context():
            allowed, reason = check_access(
                user_id=setup_users["admin"],
                user_role="admin",
                file_id=setup_file,
                file_owner_id=setup_users["user1"],
                action="decrypt"
            )
            assert allowed
            assert "Admin" in reason
    
    def test_owner_allowed_by_default(self, app, setup_users, setup_file):
        """File owners should have access by default."""
        with app.app_context():
            allowed, reason = check_access(
                user_id=setup_users["user1"],
                user_role="user",
                file_id=setup_file,
                file_owner_id=setup_users["user1"],
                action="decrypt"
            )
            assert allowed
            assert "Owner" in reason or "owner" in reason.lower()
    
    def test_non_owner_denied_by_default(self, app, setup_users, setup_file):
        """Non-owners should be denied by default."""
        with app.app_context():
            allowed, reason = check_access(
                user_id=setup_users["user2"],
                user_role="user",
                file_id=setup_file,
                file_owner_id=setup_users["user1"],
                action="decrypt"
            )
            assert not allowed
    
    def test_shared_policy(self, app, setup_users, setup_file):
        """Users in share list should have access."""
        with app.app_context():
            # Create share policy
            share_file(setup_file, setup_users["user1"], [setup_users["user2"]])
            
            allowed, reason = check_access(
                user_id=setup_users["user2"],
                user_role="user",
                file_id=setup_file,
                file_owner_id=setup_users["user1"],
                action="decrypt"
            )
            assert allowed
            assert "share" in reason.lower()
    
    def test_time_limited_policy_valid(self, app, setup_users, setup_file):
        """Time-limited policy should work within expiry."""
        with app.app_context():
            expires = datetime.now(timezone.utc) + timedelta(hours=1)
            share_file(setup_file, setup_users["user1"], [setup_users["user2"]], expires_at=expires)
            
            allowed, reason = check_access(
                user_id=setup_users["user2"],
                user_role="user",
                file_id=setup_file,
                file_owner_id=setup_users["user1"],
                action="decrypt"
            )
            assert allowed
    
    def test_time_limited_policy_expired(self, app, setup_users, setup_file):
        """Expired time-limited policy should deny access."""
        with app.app_context():
            # Set expiry in the past
            expires = datetime.now(timezone.utc) - timedelta(hours=1)
            policy = create_policy(
                media_id=setup_file,
                policy_type=PolicyType.TIME_LIMITED,
                created_by=setup_users["user1"],
                allowed_users=[setup_users["user2"]],
                expires_at=expires
            )
            
            context = PolicyContext(
                user_id=setup_users["user2"],
                user_role="user",
                file_id=setup_file,
                file_owner_id=setup_users["user1"],
                action="decrypt"
            )
            decision, reason, _ = evaluate_policy(context)
            
            # Should be expired, not allowed
            assert decision in [AccessDecision.EXPIRED, AccessDecision.DENY]
    
    def test_policy_priority(self, app, setup_users, setup_file):
        """Higher priority policies should be evaluated first."""
        with app.app_context():
            # Create low-priority deny policy (shouldn't matter)
            create_policy(
                media_id=setup_file,
                policy_type=PolicyType.OWNER_ONLY,
                created_by=setup_users["admin"],
                priority=0
            )
            
            # Create high-priority share policy
            create_policy(
                media_id=setup_file,
                policy_type=PolicyType.SHARED,
                created_by=setup_users["user1"],
                allowed_users=[setup_users["user2"]],
                priority=10
            )
            
            allowed, reason = check_access(
                user_id=setup_users["user2"],
                user_role="user",
                file_id=setup_file,
                file_owner_id=setup_users["user1"],
                action="decrypt"
            )
            assert allowed


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------
class TestKMSPolicyIntegration:
    def test_full_workflow(self, app, setup_users, setup_file):
        """Test complete KMS + Policy workflow."""
        with app.app_context():
            # 1. Store a split key
            key = generate_file_key()
            store_key(setup_file, key, n_shares=3, threshold=2)
            
            # 2. Create share policy
            share_file(setup_file, setup_users["user1"], [setup_users["user2"]])
            
            # 3. Verify user2 can access
            allowed, _ = check_access(
                user_id=setup_users["user2"],
                user_role="user",
                file_id=setup_file,
                file_owner_id=setup_users["user1"],
                action="decrypt"
            )
            assert allowed
            
            # 4. Retrieve key
            retrieved = retrieve_key(setup_file)
            assert retrieved == key
            
            # 5. Revoke key
            revoke_key(setup_file)
            
            # 6. Key should no longer be retrievable
            assert retrieve_key(setup_file) is None
