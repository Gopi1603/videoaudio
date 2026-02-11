"""
Seed script — populate database with demo users, files, shares, and audit logs.

Users created:
  1. admin / admin@example.com / admin (role: admin)
  2. RK / ramakrishna@gmail.com / Rama@123
  3. GC / gopi@gmail.com / Gopi@123
  4. shiva / shiva@gmail.com / Shiva@123
  5. priya / priya@gmail.com / Priya@123
  6. arjun / arjun@gmail.com / Arjun@123

Run: python seed_data.py
"""

import os
import sys
import uuid
import shutil
import tempfile
from datetime import datetime, timezone, timedelta

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models import User, MediaFile, AuditLog, ShareToken
from app.encryption import encrypt_file
from app.kms import store_key
from app.policy import Policy, PolicyType, share_file


def drop_all_data():
    """Drop all tables and recreate."""
    print("🗑️  Dropping all tables...")
    db.drop_all()
    db.create_all()
    print("✅ Tables recreated")


def create_users():
    """Create 5 demo users + admin."""
    print("\n👥 Creating users...")
    
    users_data = [
        {"username": "admin", "email": "admin@example.com", "password": "admin", "role": "admin"},
        {"username": "RK", "email": "ramakrishna@gmail.com", "password": "Rama@123", "role": "user"},
        {"username": "GC", "email": "gopi@gmail.com", "password": "Gopi@123", "role": "user"},
        {"username": "shiva", "email": "shiva@gmail.com", "password": "Shiva@123", "role": "user"},
        {"username": "priya", "email": "priya@gmail.com", "password": "Priya@123", "role": "user"},
        {"username": "arjun", "email": "arjun@gmail.com", "password": "Arjun@123", "role": "user"},
    ]
    
    created_users = {}
    for data in users_data:
        user = User(username=data["username"], email=data["email"], role=data["role"])
        user.set_password(data["password"])
        db.session.add(user)
        db.session.flush()
        created_users[data["username"]] = user
        print(f"  ✓ {data['username']} ({data['email']}) — Password: {data['password']}")
    
    db.session.commit()
    print(f"✅ Created {len(created_users)} users")
    return created_users


def upload_sample_files(users, sample_dir):
    """Upload sample media files as different users."""
    print("\n📁 Uploading sample files...")
    
    sample_files = sorted([f for f in os.listdir(sample_dir) if f.endswith(('.mp3', '.mp4', '.wav'))])
    if not sample_files:
        print("⚠️  No sample files found in sample/ directory")
        return {}
    
    uploaded = {}
    storage_dir = "storage"
    os.makedirs(storage_dir, exist_ok=True)
    
    # Upload files as different users - distribute across all 5 users
    user_rotation = [users["RK"], users["GC"], users["shiva"], users["priya"], users["arjun"]]
    file_owners = []
    
    for idx, filename in enumerate(sample_files):
        owner = user_rotation[idx % len(user_rotation)]
        file_owners.append((filename, owner))
    
    for filename, owner in file_owners:
        src_path = os.path.join(sample_dir, filename)
        
        # Generate stored filename
        ext = filename.rsplit(".", 1)[1].lower()
        stored_name = f"{uuid.uuid4().hex}.{ext}.enc"
        stored_path = os.path.join(storage_dir, stored_name)
        
        # Encrypt the file
        wrapped_key, meta = encrypt_file(src_path, stored_path)
        
        # Create watermark payload
        import time
        wm_payload = f"uid:{owner.id}|ts:{int(time.time())}"
        wm_id = uuid.uuid4().hex[:16]
        
        # Create MediaFile record
        media = MediaFile(
            owner_id=owner.id,
            original_filename=filename,
            stored_filename=stored_name,
            file_size=meta["encrypted_size"],
            mime_type="video/mp4" if ext == "mp4" else "audio/mpeg",
            encrypted_key=wrapped_key,
            watermark_payload=wm_payload,
            watermark_id=wm_id,
            status="encrypted",
        )
        db.session.add(media)
        db.session.flush()
        
        # Store key in KMS
        from app.encryption import unwrap_key
        raw_key = unwrap_key(wrapped_key)
        store_key(media.id, raw_key)
        
        # Log upload
        db.session.add(AuditLog(
            user_id=owner.id,
            action="upload",
            media_id=media.id,
            result="success",
            detail=f"Seeded: {filename}",
        ))
        
        uploaded[filename] = media
        print(f"  ✓ {filename} → {owner.username} (ID: {media.id})")
    
    db.session.commit()
    print(f"✅ Uploaded {len(uploaded)} files")
    return uploaded


def create_shares(users, files):
    """Create shares and tokens between users."""
    print("\n🔗 Creating shares and tokens...")
    
    if not files:
        print("⚠️  No files to share")
        return
    
    file_list = list(files.values())
    
    # Create various sharing scenarios
    share_scenarios = []
    
    # Scenario 1: First file - share with multiple users (download allowed)
    if len(file_list) > 0:
        media = file_list[0]
        recipients = [users["GC"], users["shiva"]]
        share_scenarios.append((media, recipients, True, 168, "verified", "GC"))
    
    # Scenario 2: Second file - stream-only share
    if len(file_list) > 1:
        media = file_list[1]
        recipients = [users["priya"], users["arjun"]]
        share_scenarios.append((media, recipients, False, 24, "used", "priya"))
    
    # Scenario 3: Third file - share with RK and arjun (download allowed)
    if len(file_list) > 2:
        media = file_list[2]
        recipients = [users["RK"], users["arjun"]]
        share_scenarios.append((media, recipients, True, 72, "pending", None))
    
    # Scenario 4: Fourth file - share with GC only (stream-only, short TTL)
    if len(file_list) > 3:
        media = file_list[3]
        recipients = [users["GC"]]
        share_scenarios.append((media, recipients, False, 6, "verified", "GC"))
    
    # Scenario 5: Fifth file - share with shiva and priya (download allowed)
    if len(file_list) > 4:
        media = file_list[4]
        recipients = [users["shiva"], users["priya"]]
        share_scenarios.append((media, recipients, True, 48, "used", "shiva"))
    
    # Scenario 6: Sixth file - share with all users (stream-only)
    if len(file_list) > 5:
        media = file_list[5]
        recipients = [users["RK"], users["GC"], users["shiva"]]
        share_scenarios.append((media, recipients, False, 168, "pending", None))
    
    for media, recipients, allow_download, ttl_hours, mark_status, verify_user in share_scenarios:
        # Create policy-level share
        share_file(media.id, media.owner_id, [r.id for r in recipients])
        
        # Create share tokens
        for recipient in recipients:
            token = ShareToken.create(
                media_id=media.id,
                sender_id=media.owner_id,
                recipient_id=recipient.id,
                allow_download=allow_download,
                ttl_hours=ttl_hours,
            )
            
            # Mark specific tokens based on scenario
            if verify_user and recipient.username == verify_user:
                token.verify()
                if mark_status == "used":
                    token.mark_used()
            elif mark_status == "verified" and recipient == recipients[0]:
                token.verify()
        
        db.session.add(AuditLog(
            user_id=media.owner_id,
            action="share",
            media_id=media.id,
            result="success",
            detail=f"Seeded: shared ({('download' if allow_download else 'stream-only')}) with {len(recipients)} users",
        ))
        
        recipients_str = ", ".join([r.username for r in recipients])
        access_type = "download" if allow_download else "stream-only"
        sender = [u for u in users.values() if u.id == media.owner_id][0]
        print(f"  ✓ {media.original_filename} shared by {sender.username} → {recipients_str} ({access_type})")
    
    db.session.commit()
    print("✅ Shares created")


def create_access_logs(users, files):
    """Create download/stream audit logs."""
    print("\n📊 Creating audit logs...")
    
    if not files:
        return
    
    file_list = list(files.values())
    
    # Simulate various access patterns
    actions = []
    
    # File 1 actions
    if len(file_list) > 0:
        actions.extend([
            (users["RK"], file_list[0], "download", "success", "Owner download"),
            (users["GC"], file_list[0], "share_stream", "success", "Streamed shared file"),
            (users["shiva"], file_list[0], "share_verify", "success", "Identity verified"),
        ])
    
    # File 2 actions
    if len(file_list) > 1:
        actions.extend([
            (users["GC"], file_list[1], "download", "success", "Owner download"),
            (users["priya"], file_list[1], "share_stream", "success", "Streamed via token"),
            (users["arjun"], file_list[1], "share_download_denied", "denied", "Download not permitted (stream-only)"),
        ])
    
    # File 3 actions
    if len(file_list) > 2:
        actions.extend([
            (users["shiva"], file_list[2], "download", "success", "Owner download"),
            (users["shiva"], file_list[2], "verify", "success", "Encryption verified"),
            (users["RK"], file_list[2], "share_verify", "success", "Identity verified for share"),
        ])
    
    # File 4 actions
    if len(file_list) > 3:
        actions.extend([
            (users["priya"], file_list[3], "download", "success", "Owner download"),
            (users["GC"], file_list[3], "share_stream", "success", "Streamed via token"),
        ])
    
    # File 5 actions
    if len(file_list) > 4:
        actions.extend([
            (users["arjun"], file_list[4], "download", "success", "Owner download"),
            (users["shiva"], file_list[4], "share_download", "success", "Downloaded via token"),
            (users["priya"], file_list[4], "share_stream", "success", "Streamed shared file"),
        ])
    
    # File 6 actions
    if len(file_list) > 5:
        actions.extend([
            (users["RK"], file_list[5], "download", "success", "Owner download"),
            (users["GC"], file_list[5], "share_verify_fail", "failure", "Identity check failed"),
            (users["GC"], file_list[5], "share_verify", "success", "Identity verified (retry)"),
            (users["shiva"], file_list[5], "share_stream", "success", "Streamed via token"),
        ])
    
    # Add some admin actions
    admin = users.get("admin")
    if admin and len(file_list) > 0:
        actions.extend([
            (admin, file_list[0], "download", "success", "Admin override access"),
            (admin, file_list[1], "verify", "success", "Admin verification check"),
        ])
    
    timestamp_offset = 0
    for user, media, action, result, detail in actions:
        db.session.add(AuditLog(
            user_id=user.id,
            action=action,
            media_id=media.id,
            result=result,
            detail=detail,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=timestamp_offset // 2, minutes=timestamp_offset * 10),
        ))
        timestamp_offset += 1
        print(f"  ✓ {user.username} → {action} → {media.original_filename}")
    
    db.session.commit()
    print("✅ Audit logs created")


def create_default_policy(users):
    """Create a global default owner-only policy."""
    print("\n🔒 Creating default policy...")
    
    admin = users.get("admin")
    policy = Policy(
        media_id=None,
        is_global=True,
        policy_type=PolicyType.OWNER_ONLY.value,
        priority=0,
        created_by=admin.id if admin else None,
        enabled=True,
    )
    db.session.add(policy)
    db.session.commit()
    print("✅ Default owner-only policy created")


def main():
    """Run the seed script."""
    print("=" * 60)
    print("🌱 SEED DATA SCRIPT")
    print("=" * 60)
    
    app = create_app()
    with app.app_context():
        # Step 1: Drop all data
        drop_all_data()
        
        # Step 2: Create users
        users = create_users()
        
        # Step 3: Create default policy
        create_default_policy(users)
        
        # Step 4: Upload sample files
        sample_dir = os.path.join(os.path.dirname(__file__), "sample")
        files = upload_sample_files(users, sample_dir)
        
        # Step 5: Create shares
        create_shares(users, files)
        
        # Step 6: Create audit logs
        create_access_logs(users, files)
        
        print("\n" + "=" * 60)
        print("✅ SEEDING COMPLETE!")
        print("=" * 60)
        print("\n📝 USER CREDENTIALS:")
        print("-" * 60)
        print("Username       Email                      Password")
        print("-" * 60)
        print("admin          admin@example.com          admin")
        print("RK             ramakrishna@gmail.com      Rama@123")
        print("GC             gopi@gmail.com             Gopi@123")
        print("shiva          shiva@gmail.com            Shiva@123")
        print("priya          priya@gmail.com            Priya@123")
        print("arjun          arjun@gmail.com            Arjun@123")
        print("-" * 60)
        print("\n🚀 Start the app: python run.py")
        print("🌐 Open: http://localhost:5000")
        print("\n")


if __name__ == "__main__":
    main()
