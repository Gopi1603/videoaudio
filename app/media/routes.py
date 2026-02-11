"""Media blueprint — upload, download, dashboard, profile, file detail, verify encryption, admin file listing."""

import os
import uuid
import hashlib
import tempfile

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, current_app, send_file, abort, jsonify,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models import MediaFile, AuditLog, User, ShareToken
from app.encryption import encrypt_file, decrypt_file, unwrap_key
from app.kms import store_key
from app.watermark import embed_watermark, extract_watermark, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from app.policy import check_access, share_file, revoke_share, Policy, PolicyType
from app import csrf

media_bp = Blueprint("media", __name__)


def _allowed(filename: str) -> bool:
    return "." in filename and \
        filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


# -------------------------------------------------------------------------
# Dashboard (landing page after login)
# -------------------------------------------------------------------------
@media_bp.route("/")
def dashboard():
    if not current_user.is_authenticated:
        return render_template("home.html")
    files = MediaFile.query.filter_by(owner_id=current_user.id, status="encrypted").all()

    # Fetch files shared with the current user via policies
    shared_policies = Policy.query.filter(
        Policy.policy_type.in_([PolicyType.SHARED.value, PolicyType.TIME_LIMITED.value]),
        Policy.enabled == True,
    ).all()
    shared_file_ids = set()
    for p in shared_policies:
        if current_user.id in p.get_allowed_users():
            if p.media_id:
                shared_file_ids.add(p.media_id)
    # Exclude own files, only include active encrypted files
    shared_files = MediaFile.query.filter(
        MediaFile.id.in_(shared_file_ids),
        MediaFile.owner_id != current_user.id,
        MediaFile.status == "encrypted",
    ).all() if shared_file_ids else []

    return render_template("dashboard.html", files=files, shared_files=shared_files)


# -------------------------------------------------------------------------
# Upload
# -------------------------------------------------------------------------
@media_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or f.filename == "":
            flash("No file selected.", "warning")
            return redirect(request.url)

        if not _allowed(f.filename):
            flash("File type not allowed.", "danger")
            return redirect(request.url)

        original_name = secure_filename(f.filename)
        ext = original_name.rsplit(".", 1)[1].lower()
        stored_name = f"{uuid.uuid4().hex}.{ext}.enc"
        stored_path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)

        # Build watermark payload: user ID + timestamp
        import time as _time
        wm_payload = f"uid:{current_user.id}|ts:{int(_time.time())}"

        # Save temp unencrypted copy
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}")
        wm_path = None
        wm_meta = {}
        try:
            f.save(tmp_path)

            # --- Phase 3: embed watermark before encryption ---
            if ext in AUDIO_EXTENSIONS or ext in VIDEO_EXTENSIONS:
                wm_fd, wm_path = tempfile.mkstemp(suffix=f".{ext}")
                os.close(wm_fd)
                try:
                    wm_meta = embed_watermark(tmp_path, wm_path, wm_payload)
                    encrypt_src = wm_path      # encrypt the watermarked version
                except Exception as wm_err:
                    # If watermarking fails (e.g. file too short), encrypt original
                    current_app.logger.warning(f"Watermark skipped: {wm_err}")
                    encrypt_src = tmp_path
                    wm_meta = {"skipped": str(wm_err)}
            else:
                encrypt_src = tmp_path

            wrapped_key, meta = encrypt_file(encrypt_src, stored_path)
        finally:
            os.close(tmp_fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            if wm_path and os.path.exists(wm_path):
                os.unlink(wm_path)

        media = MediaFile(
            owner_id=current_user.id,
            original_filename=original_name,
            stored_filename=stored_name,
            file_size=meta["encrypted_size"],
            mime_type=f.content_type,
            encrypted_key=wrapped_key,
            watermark_payload=wm_payload,
            watermark_id=wm_meta.get("watermark_id", ""),
        )
        db.session.add(media)
        db.session.commit()

        # Create KMS record (so Admin → Key Management is populated)
        try:
            raw_key = unwrap_key(wrapped_key)
            record = store_key(media.id, raw_key)
            media.encrypted_key = record.encrypted_key
            db.session.commit()
        except Exception as kms_err:
            current_app.logger.warning(f"KMS record not created: {kms_err}")

        db.session.add(AuditLog(
            user_id=current_user.id, action="upload",
            media_id=media.id, result="success",
            detail=(
                f"size={meta['original_size']} enc_time={meta['encryption_time_s']}s"
                f" wm_id={wm_meta.get('watermark_id','')} snr={wm_meta.get('snr_db', wm_meta.get('avg_psnr_db','n/a'))}"
            ),
        ))
        db.session.commit()

        flash(f"'{original_name}' watermarked, encrypted & stored successfully.", "success")
        return redirect(url_for("media.dashboard"))

    return render_template("upload.html")


# -------------------------------------------------------------------------
# Download / decrypt
# -------------------------------------------------------------------------
@media_bp.route("/download/<int:file_id>")
@login_required
def download(file_id: int):
    media = db.session.get(MediaFile, file_id)
    if not media or media.status != "encrypted":
        abort(404)

    # Policy Engine check (Phase 4)
    allowed, reason = check_access(
        user_id=current_user.id,
        user_role=current_user.role,
        file_id=media.id,
        file_owner_id=media.owner_id,
        action="decrypt"
    )
    
    if not allowed:
        db.session.add(AuditLog(
            user_id=current_user.id, action="download",
            media_id=media.id, result="denied",
            detail=f"Policy denied: {reason}"
        ))
        db.session.commit()
        flash(f"Access denied: {reason}", "danger")
        return redirect(url_for("media.dashboard"))

    enc_path = os.path.join(current_app.config["UPLOAD_FOLDER"], media.stored_filename)
    if not os.path.isfile(enc_path):
        abort(404)

    # Decrypt to a temp file, then stream it back
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f"_{media.original_filename}")
    try:
        os.close(tmp_fd)
        meta = decrypt_file(enc_path, tmp_path, media.encrypted_key)
    except Exception:
        os.unlink(tmp_path)
        flash("Decryption failed — file may be corrupted.", "danger")
        return redirect(url_for("media.dashboard"))

    # --- Phase 3: verify watermark after decryption ---
    wm_verify = {}
    if media.watermark_payload:
        try:
            payload_len = len(media.watermark_payload.encode("utf-8"))
            wm_verify = extract_watermark(tmp_path, payload_len)
            if wm_verify.get("payload") != media.watermark_payload:
                wm_verify["match"] = False
                current_app.logger.warning(
                    f"Watermark mismatch for file {media.id}: "
                    f"expected={media.watermark_payload!r} got={wm_verify.get('payload')!r}"
                )
            else:
                wm_verify["match"] = True
        except Exception as e:
            wm_verify = {"match": "error", "detail": str(e)}
            current_app.logger.warning(f"Watermark extraction failed for file {media.id}: {e}")

    db.session.add(AuditLog(
        user_id=current_user.id, action="download",
        media_id=media.id, result="success",
        detail=f"dec_time={meta['decryption_time_s']}s wm_match={wm_verify.get('match', 'n/a')}",
    ))
    db.session.commit()

    return send_file(
        tmp_path,
        as_attachment=True,
        download_name=media.original_filename,
    )


# -------------------------------------------------------------------------
# Download encrypted (raw) — serves the ciphertext as-is
# -------------------------------------------------------------------------
@media_bp.route("/download-encrypted/<int:file_id>")
@login_required
def download_encrypted(file_id: int):
    media = db.session.get(MediaFile, file_id)
    if not media or media.status != "encrypted":
        abort(404)

    # Policy Engine check — same as decrypt download
    allowed, reason = check_access(
        user_id=current_user.id,
        user_role=current_user.role,
        file_id=media.id,
        file_owner_id=media.owner_id,
        action="decrypt"
    )
    if not allowed:
        flash(f"Access denied: {reason}", "danger")
        return redirect(url_for("media.dashboard"))

    enc_path = os.path.join(current_app.config["UPLOAD_FOLDER"], media.stored_filename)
    if not os.path.isfile(enc_path):
        abort(404)

    # Serve the raw encrypted file with .enc extension so it's clearly ciphertext
    name_parts = media.original_filename.rsplit(".", 1)
    enc_name = f"{name_parts[0]}_encrypted.{name_parts[1]}.enc" if len(name_parts) == 2 else f"{media.original_filename}.enc"

    db.session.add(AuditLog(
        user_id=current_user.id, action="download_encrypted",
        media_id=media.id, result="success",
        detail="Raw encrypted file downloaded (ciphertext)",
    ))
    db.session.commit()

    return send_file(
        enc_path,
        as_attachment=True,
        download_name=enc_name,
        mimetype="application/octet-stream",
    )


# -------------------------------------------------------------------------
# Delete
# -------------------------------------------------------------------------
@media_bp.route("/delete/<int:file_id>", methods=["POST"])
@login_required
def delete(file_id: int):
    media = db.session.get(MediaFile, file_id)
    if not media:
        abort(404)

    if media.owner_id != current_user.id and not current_user.is_admin:
        abort(403)

    enc_path = os.path.join(current_app.config["UPLOAD_FOLDER"], media.stored_filename)
    if os.path.isfile(enc_path):
        os.unlink(enc_path)

    media.status = "deleted"
    media.encrypted_key = None
    db.session.add(AuditLog(
        user_id=current_user.id, action="delete",
        media_id=media.id, result="success",
    ))
    db.session.commit()

    flash("File deleted.", "info")
    return redirect(url_for("media.dashboard"))


# -------------------------------------------------------------------------
# Admin — list all files
# -------------------------------------------------------------------------
@media_bp.route("/admin/files")
@login_required
def admin_files():
    if not current_user.is_admin:
        abort(403)
    files = MediaFile.query.order_by(MediaFile.created_at.desc()).all()
    return render_template("admin_files.html", files=files)


# -------------------------------------------------------------------------
# Profile page
# -------------------------------------------------------------------------
@media_bp.route("/profile")
@login_required
def profile():
    total_files = MediaFile.query.filter_by(
        owner_id=current_user.id, status="encrypted"
    ).count()
    total_size = db.session.query(
        db.func.coalesce(db.func.sum(MediaFile.file_size), 0)
    ).filter_by(owner_id=current_user.id, status="encrypted").scalar()
    recent_logs = AuditLog.query.filter_by(
        user_id=current_user.id
    ).order_by(AuditLog.timestamp.desc()).limit(20).all()
    return render_template(
        "profile.html",
        total_files=total_files,
        total_size=total_size,
        recent_logs=recent_logs,
    )


# -------------------------------------------------------------------------
# File detail page
# -------------------------------------------------------------------------
@media_bp.route("/file/<int:file_id>")
@login_required
def file_detail(file_id: int):
    media = db.session.get(MediaFile, file_id)
    if not media:
        abort(404)

    # Allow owner, admin, or users the file is shared with
    is_owner = media.owner_id == current_user.id
    is_admin = current_user.is_admin
    shared_policies = Policy.query.filter(
        Policy.media_id == media.id,
        Policy.policy_type.in_([PolicyType.SHARED.value, PolicyType.TIME_LIMITED.value]),
        Policy.enabled == True
    ).all()
    shared_user_ids = set()
    for p in shared_policies:
        shared_user_ids.update(p.get_allowed_users())
    is_shared_with_me = current_user.id in shared_user_ids

    if not is_owner and not is_admin and not is_shared_with_me:
        abort(403)

    # Fetch audit logs for this file
    logs = AuditLog.query.filter_by(media_id=media.id).order_by(
        AuditLog.timestamp.desc()
    ).limit(20).all()

    # For owner/admin: get users list for sharing UI
    all_users = []
    if is_owner or is_admin:
        all_users = User.query.filter(User.id != media.owner_id).order_by(User.username).all()

    # Get users currently shared with (resolve IDs to objects)
    shared_users = User.query.filter(User.id.in_(shared_user_ids)).all() if shared_user_ids else []

    return render_template(
        "file_detail.html", media=media, logs=logs,
        all_users=all_users, shared_users=shared_users,
        is_owner=is_owner, is_shared_with_me=is_shared_with_me,
    )


# -------------------------------------------------------------------------
# Share file with users
# -------------------------------------------------------------------------
@media_bp.route("/share/<int:file_id>", methods=["POST"])
@login_required
def share(file_id: int):
    media = db.session.get(MediaFile, file_id)
    if not media:
        abort(404)
    if media.owner_id != current_user.id and not current_user.is_admin:
        abort(403)

    user_ids = request.form.getlist("user_ids", type=int)
    if not user_ids:
        flash("Select at least one user to share with.", "warning")
        return redirect(url_for("media.file_detail", file_id=media.id))

    # Validate user IDs exist and aren't the owner
    valid_ids = [
        u.id for u in User.query.filter(User.id.in_(user_ids)).all()
        if u.id != media.owner_id
    ]

    # Permissions from form
    permission = request.form.get("permission", "stream")
    allow_download = permission == "download"
    ttl_hours = request.form.get("ttl_hours", 24, type=int)

    if valid_ids:
        # Create policy-level share (existing behaviour)
        share_file(media.id, current_user.id, valid_ids)

        # Create per-user ShareToken for encrypted delivery
        created_tokens = []
        for uid in valid_ids:
            tok = ShareToken.create(
                media_id=media.id,
                sender_id=current_user.id,
                recipient_id=uid,
                allow_download=allow_download,
                ttl_hours=ttl_hours,
            )
            created_tokens.append(tok)

        usernames = [u.username for u in User.query.filter(User.id.in_(valid_ids)).all()]
        db.session.add(AuditLog(
            user_id=current_user.id, action="share",
            media_id=media.id, result="success",
            detail=f"Shared with: {', '.join(usernames)} | download={allow_download} ttl={ttl_hours}h",
        ))
        db.session.commit()
        flash(f"File shared with {', '.join(usernames)} via secure token (expires in {ttl_hours}h).", "success")
    else:
        flash("No valid users selected.", "warning")

    return redirect(url_for("media.file_detail", file_id=media.id))


# -------------------------------------------------------------------------
# Revoke share for a user
# -------------------------------------------------------------------------
@media_bp.route("/revoke/<int:file_id>/<int:user_id>", methods=["POST"])
@login_required
def revoke(file_id: int, user_id: int):
    media = db.session.get(MediaFile, file_id)
    if not media:
        abort(404)
    if media.owner_id != current_user.id and not current_user.is_admin:
        abort(403)

    target_user = db.session.get(User, user_id)
    revoke_share(media.id, user_id)

    # Also revoke any active ShareTokens for this user + file
    active_tokens = ShareToken.query.filter(
        ShareToken.media_id == media.id,
        ShareToken.recipient_id == user_id,
        ShareToken.status != "revoked",
    ).all()
    for tok in active_tokens:
        tok.revoke()

    db.session.add(AuditLog(
        user_id=current_user.id, action="revoke_share",
        media_id=media.id, result="success",
        detail=f"Revoked access + {len(active_tokens)} token(s) for: {target_user.username if target_user else user_id}",
    ))
    db.session.commit()

    flash(f"Access revoked for {target_user.username if target_user else 'user'}.", "info")
    return redirect(url_for("media.file_detail", file_id=media.id))


# -------------------------------------------------------------------------
# Verify Encryption — prove stored file is really encrypted
# -------------------------------------------------------------------------
@media_bp.route("/verify/<int:file_id>")
@login_required
def verify_encryption(file_id: int):
    media = db.session.get(MediaFile, file_id)
    if not media:
        abort(404)
    if media.owner_id != current_user.id and not current_user.is_admin:
        abort(403)

    from app.kms import KeyRecord

    checks = {}

    # 1. File on disk
    enc_path = os.path.join(current_app.config["UPLOAD_FOLDER"], media.stored_filename)
    file_exists = os.path.isfile(enc_path)
    checks["file_on_disk"] = file_exists

    if file_exists:
        # 2. Read raw header — AES-GCM output starts with 12-byte nonce (random)
        with open(enc_path, "rb") as fh:
            raw_header = fh.read(64)
            fh.seek(0, 2)
            raw_size = fh.tell()

        checks["stored_filename"] = media.stored_filename
        checks["stored_size_bytes"] = raw_size
        checks["raw_hex_header"] = raw_header[:32].hex()

        # 3. Check if file is playable (valid media headers)
        # Known magic bytes for media formats
        magic_sigs = {
            b'\x49\x44\x33': 'MP3 (ID3)',
            b'\xff\xfb': 'MP3',
            b'\xff\xf3': 'MP3',
            b'\x52\x49\x46\x46': 'WAV/AVI (RIFF)',
            b'\x4f\x67\x67\x53': 'OGG',
            b'\x66\x4c\x61\x43': 'FLAC',
            b'\x00\x00\x00': 'MP4/MOV (possible)',
            b'\x1a\x45\xdf\xa3': 'MKV/WebM',
        }
        detected_format = None
        for sig, fmt in magic_sigs.items():
            if raw_header[:len(sig)] == sig:
                detected_format = fmt
                break

        checks["raw_file_playable"] = detected_format is not None
        checks["detected_format"] = detected_format  # None = not recognisable = encrypted ✓

        # 4. Shannon entropy of first 1024 bytes (encrypted data ≈ 7.9+ bits/byte)
        with open(enc_path, "rb") as fh:
            sample = fh.read(1024)
        if sample:
            import math
            freq = [0] * 256
            for b in sample:
                freq[b] += 1
            entropy = 0.0
            for count in freq:
                if count > 0:
                    p = count / len(sample)
                    entropy -= p * math.log2(p)
            checks["entropy_bits_per_byte"] = round(entropy, 3)
            checks["entropy_verdict"] = (
                "high (encrypted)" if entropy > 7.5 else "medium" if entropy > 6.0 else "low (likely unencrypted)"
            )

        # 5. SHA-256 hash of stored (encrypted) file
        sha = hashlib.sha256()
        with open(enc_path, "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                sha.update(chunk)
        checks["sha256_encrypted"] = sha.hexdigest()

    # 6. Encryption key present?
    checks["encrypted_key_present"] = bool(media.encrypted_key)
    if media.encrypted_key:
        checks["key_token_preview"] = media.encrypted_key[:20] + "…" + media.encrypted_key[-8:]

    # 7. KMS record exists?
    kms_record = KeyRecord.query.filter_by(media_id=media.id).first()
    checks["kms_record_exists"] = kms_record is not None
    if kms_record:
        checks["kms_status"] = kms_record.status
        checks["kms_total_shares"] = kms_record.total_shares
        checks["kms_threshold"] = kms_record.threshold
        checks["kms_shares_count"] = kms_record.shares.count()

    # 8. Watermark info
    checks["watermark_embedded"] = bool(media.watermark_id)
    checks["watermark_payload"] = media.watermark_payload or "—"
    checks["watermark_id"] = media.watermark_id or "—"

    # 9. Can we actually decrypt? (quick test — unwrap key only, don't decrypt full file)
    try:
        raw_key = unwrap_key(media.encrypted_key)
        checks["fernet_unwrap"] = True
        checks["aes_key_length_bits"] = len(raw_key) * 8
    except Exception as e:
        checks["fernet_unwrap"] = False
        checks["fernet_error"] = str(e)

    # 10. Status
    checks["db_status"] = media.status

    # Log the verification
    db.session.add(AuditLog(
        user_id=current_user.id, action="verify",
        media_id=media.id, result="success",
    ))
    db.session.commit()

    return render_template("verify_encryption.html", media=media, checks=checks)


# -------------------------------------------------------------------------
# REST API — JSON endpoints for all user actions
# -------------------------------------------------------------------------
@media_bp.route("/api/files")
@login_required
@csrf.exempt
def api_files():
    """API: list current user's encrypted files."""
    files = MediaFile.query.filter_by(
        owner_id=current_user.id, status="encrypted"
    ).all()
    return jsonify([
        {
            "id": f.id,
            "filename": f.original_filename,
            "size": f.file_size,
            "mime_type": f.mime_type,
            "watermark_id": f.watermark_id,
            "created_at": f.created_at.isoformat(),
        }
        for f in files
    ])


@media_bp.route("/api/files/<int:file_id>")
@login_required
@csrf.exempt
def api_file_detail(file_id: int):
    """API: single file detail."""
    media = db.session.get(MediaFile, file_id)
    if not media:
        return jsonify({"error": "File not found"}), 404
    if media.owner_id != current_user.id and not current_user.is_admin:
        return jsonify({"error": "Forbidden"}), 403
    return jsonify({
        "id": media.id,
        "filename": media.original_filename,
        "size": media.file_size,
        "mime_type": media.mime_type,
        "status": media.status,
        "watermark_id": media.watermark_id,
        "watermark_payload": media.watermark_payload,
        "created_at": media.created_at.isoformat(),
    })


@media_bp.route("/api/upload", methods=["POST"])
@login_required
@csrf.exempt
def api_upload():
    """API: upload & encrypt a file (returns JSON)."""
    f = request.files.get("file")
    if not f or f.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not _allowed(f.filename):
        return jsonify({"error": "File type not allowed"}), 400

    original_name = secure_filename(f.filename)
    ext = original_name.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}.enc"
    stored_path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)

    import time as _time
    wm_payload = f"uid:{current_user.id}|ts:{int(_time.time())}"

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}")
    wm_path = None
    wm_meta: dict = {}
    try:
        f.save(tmp_path)
        if ext in AUDIO_EXTENSIONS or ext in VIDEO_EXTENSIONS:
            wm_fd, wm_path = tempfile.mkstemp(suffix=f".{ext}")
            os.close(wm_fd)
            try:
                wm_meta = embed_watermark(tmp_path, wm_path, wm_payload)
                encrypt_src = wm_path
            except Exception as wm_err:
                current_app.logger.warning(f"Watermark skipped: {wm_err}")
                encrypt_src = tmp_path
                wm_meta = {"skipped": str(wm_err)}
        else:
            encrypt_src = tmp_path
        wrapped_key, meta = encrypt_file(encrypt_src, stored_path)
    finally:
        os.close(tmp_fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if wm_path and os.path.exists(wm_path):
            os.unlink(wm_path)

    media = MediaFile(
        owner_id=current_user.id,
        original_filename=original_name,
        stored_filename=stored_name,
        file_size=meta["encrypted_size"],
        mime_type=f.content_type,
        encrypted_key=wrapped_key,
        watermark_payload=wm_payload,
        watermark_id=wm_meta.get("watermark_id", ""),
    )
    db.session.add(media)
    db.session.commit()

    db.session.add(AuditLog(
        user_id=current_user.id, action="upload",
        media_id=media.id, result="success",
        detail=f"api_upload size={meta['original_size']}",
    ))
    db.session.commit()

    return jsonify({
        "id": media.id,
        "filename": media.original_filename,
        "size": media.file_size,
        "watermark_id": wm_meta.get("watermark_id", ""),
    }), 201


@media_bp.route("/api/files/<int:file_id>", methods=["DELETE"])
@login_required
@csrf.exempt
def api_delete(file_id: int):
    """API: delete a file."""
    media = db.session.get(MediaFile, file_id)
    if not media:
        return jsonify({"error": "File not found"}), 404
    if media.owner_id != current_user.id and not current_user.is_admin:
        return jsonify({"error": "Forbidden"}), 403

    enc_path = os.path.join(current_app.config["UPLOAD_FOLDER"], media.stored_filename)
    if os.path.isfile(enc_path):
        os.unlink(enc_path)

    media.status = "deleted"
    media.encrypted_key = None
    db.session.add(AuditLog(
        user_id=current_user.id, action="delete",
        media_id=media.id, result="success", detail="api_delete",
    ))
    db.session.commit()
    return jsonify({"message": "File deleted"}), 200
