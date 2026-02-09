"""Admin blueprint for key management and policy control."""

from functools import wraps
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from app import db
from app import csrf
from app.models import User, MediaFile, AuditLog
from app.kms import (
    KeyRecord, KeyShare, get_key_info, list_keys, revoke_key, 
    store_key, generate_file_key, retrieve_key
)
from app.policy import (
    Policy, PolicyLog, PolicyType, check_access, create_policy,
    update_policy, delete_policy, get_file_policies, share_file, revoke_share
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for("media.dashboard"))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# Key Management Routes
# ---------------------------------------------------------------------------

@admin_bp.route("/keys")
@login_required
@admin_required
def key_management():
    """Key management dashboard."""
    keys = list_keys()
    return render_template("admin/keys.html", keys=keys)


@admin_bp.route("/keys/<int:media_id>")
@login_required
@admin_required
def key_detail(media_id):
    """View details of a specific key."""
    key_info = get_key_info(media_id)
    if not key_info:
        flash("Key not found.", "warning")
        return redirect(url_for("admin.key_management"))
    
    media = MediaFile.query.get(media_id)
    return render_template("admin/key_detail.html", key=key_info, media=media)


@admin_bp.route("/keys/<int:media_id>/revoke", methods=["POST"])
@login_required
@admin_required
def revoke_key_route(media_id):
    """Revoke a key (makes file undecryptable)."""
    success = revoke_key(media_id)
    
    # Log the action
    log = AuditLog(
        user_id=current_user.id,
        action="key_revoke",
        media_id=media_id,
        result="success" if success else "failed",
        detail=f"Admin {current_user.username} revoked key"
    )
    db.session.add(log)
    db.session.commit()
    
    if success:
        flash(f"Key for file #{media_id} has been revoked.", "success")
    else:
        flash("Failed to revoke key.", "danger")
    
    return redirect(url_for("admin.key_management"))


@admin_bp.route("/keys/<int:media_id>/split", methods=["POST"])
@login_required
@admin_required
def split_key_route(media_id):
    """Split an existing key using Shamir's Secret Sharing."""
    n_shares = request.form.get("n_shares", 3, type=int)
    threshold = request.form.get("threshold", 2, type=int)
    
    # Get current key
    key = retrieve_key(media_id)
    if not key:
        flash("Could not retrieve key for splitting.", "danger")
        return redirect(url_for("admin.key_detail", media_id=media_id))
    
    # Revoke old key record
    revoke_key(media_id)
    
    # Create new split key
    holder_ids_str = request.form.get("holder_ids", "")
    holder_ids = [int(x.strip()) for x in holder_ids_str.split(",") if x.strip()]
    
    store_key(media_id, key, n_shares=n_shares, threshold=threshold, holder_ids=holder_ids)
    
    # Log the action
    log = AuditLog(
        user_id=current_user.id,
        action="key_split",
        media_id=media_id,
        result="success",
        detail=f"Split into {n_shares} shares with threshold {threshold}"
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f"Key split into {n_shares} shares (threshold: {threshold}).", "success")
    return redirect(url_for("admin.key_detail", media_id=media_id))


# ---------------------------------------------------------------------------
# Policy Management Routes
# ---------------------------------------------------------------------------

@admin_bp.route("/policies")
@login_required
@admin_required
def policy_management():
    """Policy management dashboard."""
    policies = Policy.query.order_by(Policy.created_at.desc()).all()
    files = MediaFile.query.filter_by(status="encrypted").all()
    users = User.query.all()
    return render_template("admin/policies.html", policies=policies, files=files, users=users)


@admin_bp.route("/policies/create", methods=["POST"])
@login_required
@admin_required
def create_policy_route():
    """Create a new policy."""
    media_id = request.form.get("media_id", type=int)
    policy_type = request.form.get("policy_type", PolicyType.OWNER_ONLY.value)
    
    kwargs = {
        "priority": request.form.get("priority", 0, type=int),
        "enabled": request.form.get("enabled", "on") == "on"
    }
    
    # Handle allowed_users for SHARED policies
    if policy_type in [PolicyType.SHARED.value, PolicyType.TIME_LIMITED.value]:
        user_ids = request.form.getlist("allowed_users")
        kwargs["allowed_users"] = [int(uid) for uid in user_ids if uid]
    
    # Handle expires_at for TIME_LIMITED
    if policy_type == PolicyType.TIME_LIMITED.value:
        expires_str = request.form.get("expires_at")
        if expires_str:
            kwargs["expires_at"] = datetime.fromisoformat(expires_str)
    
    # Handle threshold for MULTI_PARTY
    if policy_type == PolicyType.MULTI_PARTY.value:
        kwargs["required_approvals"] = request.form.get("required_approvals", 2, type=int)
    
    # Handle custom rule
    if policy_type == PolicyType.CUSTOM.value:
        kwargs["rule_expression"] = request.form.get("rule_expression", "")
    
    policy = create_policy(
        media_id=media_id if media_id else None,
        policy_type=PolicyType(policy_type),
        created_by=current_user.id,
        **kwargs
    )
    
    # Log the action
    log = AuditLog(
        user_id=current_user.id,
        action="policy_create",
        media_id=media_id,
        result="success",
        detail=f"Created {policy_type} policy"
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f"Policy created successfully.", "success")
    return redirect(url_for("admin.policy_management"))


@admin_bp.route("/policies/<int:policy_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_policy(policy_id):
    """Enable or disable a policy."""
    policy = Policy.query.get_or_404(policy_id)
    policy.enabled = not policy.enabled
    db.session.commit()
    
    status = "enabled" if policy.enabled else "disabled"
    flash(f"Policy {status}.", "success")
    return redirect(url_for("admin.policy_management"))


@admin_bp.route("/policies/<int:policy_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_policy_route(policy_id):
    """Delete a policy."""
    success = delete_policy(policy_id)
    
    if success:
        flash("Policy deleted.", "success")
    else:
        flash("Failed to delete policy.", "danger")
    
    return redirect(url_for("admin.policy_management"))


# ---------------------------------------------------------------------------
# File Sharing Routes
# ---------------------------------------------------------------------------

@admin_bp.route("/files/<int:media_id>/share", methods=["POST"])
@login_required
@admin_required
def share_file_route(media_id):
    """Share a file with specific users."""
    media = MediaFile.query.get_or_404(media_id)
    
    user_ids = request.form.getlist("user_ids")
    user_ids = [int(uid) for uid in user_ids if uid]
    
    expires_str = request.form.get("expires_at")
    expires_at = datetime.fromisoformat(expires_str) if expires_str else None
    
    share_file(media_id, media.owner_id, user_ids, expires_at)
    
    # Log the action
    log = AuditLog(
        user_id=current_user.id,
        action="file_share",
        media_id=media_id,
        result="success",
        detail=f"Shared with users: {user_ids}"
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f"File shared with {len(user_ids)} user(s).", "success")
    return redirect(url_for("admin.policy_management"))


# ---------------------------------------------------------------------------
# Audit Log Routes
# ---------------------------------------------------------------------------

@admin_bp.route("/audit")
@login_required
@admin_required
def audit_logs():
    """View audit logs."""
    page = request.args.get("page", 1, type=int)
    
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    
    policy_logs = PolicyLog.query.order_by(PolicyLog.timestamp.desc()).limit(100).all()
    
    return render_template("admin/audit.html", logs=logs, policy_logs=policy_logs)


# ---------------------------------------------------------------------------
# User Management Routes
# ---------------------------------------------------------------------------

@admin_bp.route("/users")
@login_required
@admin_required
def user_management():
    """User management dashboard."""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)


@admin_bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
@login_required
@admin_required
def toggle_admin(user_id):
    """Toggle admin status for a user."""
    if user_id == current_user.id:
        flash("You cannot change your own admin status.", "warning")
        return redirect(url_for("admin.user_management"))
    
    user = User.query.get_or_404(user_id)
    user.role = "user" if user.role == "admin" else "admin"
    db.session.commit()
    
    flash(f"User {user.username} is now {'an admin' if user.is_admin else 'a regular user'}.", "success")
    return redirect(url_for("admin.user_management"))


# ---------------------------------------------------------------------------
# API Endpoints (JSON)
# ---------------------------------------------------------------------------

@admin_bp.route("/api/keys")
@login_required
@admin_required
@csrf.exempt
def api_list_keys():
    """API: List all keys."""
    status = request.args.get("status")
    keys = list_keys(status=status)
    return jsonify(keys)


@admin_bp.route("/api/keys/<int:media_id>")
@login_required
@admin_required
@csrf.exempt
def api_key_detail(media_id):
    """API: Get key details."""
    key_info = get_key_info(media_id)
    if not key_info:
        return jsonify({"error": "Key not found"}), 404
    return jsonify(key_info)


@admin_bp.route("/api/check-access", methods=["POST"])
@login_required
@admin_required
@csrf.exempt
def api_check_access():
    """API: Check if a user has access to a file."""
    data = request.get_json()
    
    allowed, reason = check_access(
        user_id=data.get("user_id"),
        user_role=data.get("user_role", "user"),
        file_id=data.get("file_id"),
        file_owner_id=data.get("file_owner_id"),
        action=data.get("action", "decrypt")
    )
    
    return jsonify({"allowed": allowed, "reason": reason})
