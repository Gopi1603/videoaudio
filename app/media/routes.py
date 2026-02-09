"""Media blueprint — upload, download, dashboard, admin file listing."""

import os
import uuid
import tempfile

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, current_app, send_file, abort,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models import MediaFile, AuditLog
from app.encryption import encrypt_file, decrypt_file
from app.watermark import embed_watermark, extract_watermark, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS

media_bp = Blueprint("media", __name__)


def _allowed(filename: str) -> bool:
    return "." in filename and \
        filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


# -------------------------------------------------------------------------
# Dashboard (landing page after login)
# -------------------------------------------------------------------------
@media_bp.route("/")
@login_required
def dashboard():
    files = MediaFile.query.filter_by(owner_id=current_user.id, status="encrypted").all()
    return render_template("dashboard.html", files=files)


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

    # Basic ownership check (policy engine comes in Phase 4)
    if media.owner_id != current_user.id and not current_user.is_admin:
        db.session.add(AuditLog(
            user_id=current_user.id, action="download",
            media_id=media.id, result="denied",
        ))
        db.session.commit()
        abort(403)

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
