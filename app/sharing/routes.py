"""Sharing blueprint — token-based secure media sharing with identity verification.

Endpoints:
  /sharing/access/<token>         – Landing page: auth gate + identity check
  /sharing/verify/<token>         – POST: verify identity (re-enter password)
  /sharing/stream/<token>         – Stream-only playback (no download)
  /sharing/download/<token>       – Download decrypted file (if policy allows)
  /sharing/revoke/<token>         – POST: sender/admin revoke a token
  /sharing/my-shares              – Receiver: view all tokens shared with me
  /sharing/sent                   – Sender: view all tokens I created
"""

import os
import tempfile
from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, current_app, send_file, abort, jsonify, Response,
)
from flask_login import login_required, current_user

from app import db, csrf
from app.models import MediaFile, AuditLog, User, ShareToken
from app.encryption import decrypt_file, unwrap_key, decrypt_bytes

sharing_bp = Blueprint("sharing", __name__, url_prefix="/sharing")


# -------------------------------------------------------------------------
# Access landing — receiver clicks the share link
# -------------------------------------------------------------------------
@sharing_bp.route("/access/<token>")
@login_required
def access(token: str):
    """Show the identity-verification gate for a share token."""
    st = ShareToken.query.filter_by(token=token).first_or_404()

    # Only the intended recipient can use the token
    if st.recipient_id != current_user.id:
        flash("This share link was not intended for your account.", "danger")
        return redirect(url_for("media.dashboard"))

    if st.status == "revoked":
        flash("This share link has been revoked by the owner.", "warning")
        return redirect(url_for("media.dashboard"))

    if st.is_expired:
        flash("This share link has expired.", "warning")
        return redirect(url_for("media.dashboard"))

    media = db.session.get(MediaFile, st.media_id)
    if not media or media.status != "encrypted":
        flash("The shared file is no longer available.", "warning")
        return redirect(url_for("media.dashboard"))

    already_verified = st.status in ("verified", "used")

    return render_template(
        "sharing/access.html",
        token=st, media=media,
        already_verified=already_verified,
    )


# -------------------------------------------------------------------------
# Identity verification — receiver re-enters password to unlock
# -------------------------------------------------------------------------
@sharing_bp.route("/verify/<token>", methods=["POST"])
@login_required
def verify(token: str):
    """Verify receiver identity by re-entering their password."""
    st = ShareToken.query.filter_by(token=token).first_or_404()

    if st.recipient_id != current_user.id:
        abort(403)
    if not st.is_valid:
        flash("Token is no longer valid.", "warning")
        return redirect(url_for("media.dashboard"))

    password = request.form.get("password", "")
    if not current_user.check_password(password):
        db.session.add(AuditLog(
            user_id=current_user.id, action="share_verify_fail",
            media_id=st.media_id, result="failure",
            detail=f"Identity check failed for token {st.token[:8]}…",
        ))
        db.session.commit()
        flash("Identity verification failed. Please enter your correct password.", "danger")
        return redirect(url_for("sharing.access", token=token))

    st.verify()

    db.session.add(AuditLog(
        user_id=current_user.id, action="share_verify",
        media_id=st.media_id, result="success",
        detail=f"Identity verified for token {st.token[:8]}…",
    ))
    db.session.commit()

    flash("Identity verified! You can now access the file.", "success")
    return redirect(url_for("sharing.access", token=token))


# -------------------------------------------------------------------------
# Stream — in-browser playback (no download button)
# -------------------------------------------------------------------------
@sharing_bp.route("/stream/<token>")
@login_required
def stream(token: str):
    """Stream the decrypted media in-browser (no download)."""
    st = ShareToken.query.filter_by(token=token).first_or_404()

    if st.recipient_id != current_user.id and not current_user.is_admin:
        abort(403)
    if st.status not in ("verified", "used"):
        flash("Please verify your identity first.", "warning")
        return redirect(url_for("sharing.access", token=token))
    if not st.is_valid:
        flash("Token is no longer valid.", "warning")
        return redirect(url_for("media.dashboard"))

    media = db.session.get(MediaFile, st.media_id)
    if not media or media.status != "encrypted":
        abort(404)

    enc_path = os.path.join(current_app.config["UPLOAD_FOLDER"], media.stored_filename)
    if not os.path.isfile(enc_path):
        abort(404)

    # Decrypt to temp file
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f"_{media.original_filename}")
    try:
        os.close(tmp_fd)
        decrypt_file(enc_path, tmp_path, media.encrypted_key)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        flash("Decryption failed.", "danger")
        return redirect(url_for("sharing.access", token=token))

    st.mark_used()

    db.session.add(AuditLog(
        user_id=current_user.id, action="share_stream",
        media_id=media.id, result="success",
        detail=f"Streamed via token {st.token[:8]}…",
    ))
    db.session.commit()

    return render_template(
        "sharing/player.html",
        token=st, media=media,
        stream_url=url_for("sharing.stream_data", token=token),
    )


@sharing_bp.route("/stream-data/<token>")
@login_required
def stream_data(token: str):
    """Serve the actual decrypted bytes for the HTML5 player."""
    st = ShareToken.query.filter_by(token=token).first_or_404()

    if st.recipient_id != current_user.id and not current_user.is_admin:
        abort(403)
    if st.status not in ("verified", "used"):
        abort(403)
    if not st.is_valid:
        abort(403)

    media = db.session.get(MediaFile, st.media_id)
    if not media or media.status != "encrypted":
        abort(404)

    enc_path = os.path.join(current_app.config["UPLOAD_FOLDER"], media.stored_filename)
    if not os.path.isfile(enc_path):
        abort(404)

    # Decrypt in memory
    try:
        file_key = unwrap_key(media.encrypted_key)
        with open(enc_path, "rb") as f:
            blob = f.read()
        plaintext = decrypt_bytes(blob, file_key)
    except Exception:
        abort(500)

    mime = media.mime_type or "application/octet-stream"
    return Response(plaintext, mimetype=mime, headers={
        "Content-Disposition": "inline",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    })


# -------------------------------------------------------------------------
# Download — only if allow_download is set on the token
# -------------------------------------------------------------------------
@sharing_bp.route("/download/<token>")
@login_required
def download(token: str):
    """Download the decrypted file if policy allows."""
    st = ShareToken.query.filter_by(token=token).first_or_404()

    if st.recipient_id != current_user.id and not current_user.is_admin:
        abort(403)
    if st.status not in ("verified", "used"):
        flash("Please verify your identity first.", "warning")
        return redirect(url_for("sharing.access", token=token))
    if not st.is_valid:
        flash("Token is no longer valid.", "warning")
        return redirect(url_for("media.dashboard"))

    if not st.allow_download:
        db.session.add(AuditLog(
            user_id=current_user.id, action="share_download_denied",
            media_id=st.media_id, result="denied",
            detail=f"Download not permitted (stream-only) token {st.token[:8]}…",
        ))
        db.session.commit()
        flash("Download is not allowed for this share. Stream-only access.", "warning")
        return redirect(url_for("sharing.access", token=token))

    media = db.session.get(MediaFile, st.media_id)
    if not media or media.status != "encrypted":
        abort(404)

    enc_path = os.path.join(current_app.config["UPLOAD_FOLDER"], media.stored_filename)
    if not os.path.isfile(enc_path):
        abort(404)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f"_{media.original_filename}")
    try:
        os.close(tmp_fd)
        decrypt_file(enc_path, tmp_path, media.encrypted_key)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        flash("Decryption failed.", "danger")
        return redirect(url_for("sharing.access", token=token))

    st.mark_used()

    db.session.add(AuditLog(
        user_id=current_user.id, action="share_download",
        media_id=media.id, result="success",
        detail=f"Downloaded via token {st.token[:8]}…",
    ))
    db.session.commit()

    return send_file(tmp_path, as_attachment=True, download_name=media.original_filename)


# -------------------------------------------------------------------------
# Revoke — sender or admin revokes a token
# -------------------------------------------------------------------------
@sharing_bp.route("/revoke-token/<token>", methods=["POST"])
@login_required
def revoke_token(token: str):
    """Revoke a share token."""
    st = ShareToken.query.filter_by(token=token).first_or_404()

    if st.sender_id != current_user.id and not current_user.is_admin:
        abort(403)

    st.revoke()

    db.session.add(AuditLog(
        user_id=current_user.id, action="share_revoke",
        media_id=st.media_id, result="success",
        detail=f"Revoked token {st.token[:8]}… for user {st.recipient_id}",
    ))
    db.session.commit()

    flash("Share token revoked.", "info")
    return redirect(request.referrer or url_for("media.dashboard"))


# -------------------------------------------------------------------------
# My Shares — what's been shared with me
# -------------------------------------------------------------------------
@sharing_bp.route("/received")
@login_required
def received():
    """View all share tokens the current user has received."""
    tokens = ShareToken.query.filter_by(recipient_id=current_user.id)\
        .order_by(ShareToken.created_at.desc()).all()
    return render_template("sharing/received.html", tokens=tokens)


# -------------------------------------------------------------------------
# Sent Shares — what I've shared out
# -------------------------------------------------------------------------
@sharing_bp.route("/sent")
@login_required
def sent():
    """View all share tokens the current user has sent."""
    tokens = ShareToken.query.filter_by(sender_id=current_user.id)\
        .order_by(ShareToken.created_at.desc()).all()
    return render_template("sharing/sent.html", tokens=tokens)
