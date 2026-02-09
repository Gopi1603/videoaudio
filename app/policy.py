"""
Policy Engine — Role-based and attribute-based access control for media files.

Features:
  • Define access policies (who can decrypt what)
  • Role-based access control (RBAC): admin, user roles
  • Attribute-based access control (ABAC): ownership, time-based, etc.
  • Policy evaluation with detailed logging
  • Default policies for common scenarios

Policy Types:
  • OWNER_ONLY: Only the file owner can decrypt
  • ADMIN_OVERRIDE: Admins can decrypt any file
  • SHARED: Specific users can decrypt (via share list)
  • TIME_LIMITED: Access expires after a certain time
  • MULTI_PARTY: Requires multiple approvals (threshold)
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from dataclasses import dataclass

from app import db


class PolicyType(str, Enum):
    """Types of access policies."""
    OWNER_ONLY = "owner_only"
    ADMIN_OVERRIDE = "admin_override"
    SHARED = "shared"
    TIME_LIMITED = "time_limited"
    MULTI_PARTY = "multi_party"
    CUSTOM = "custom"


class AccessDecision(str, Enum):
    """Result of policy evaluation."""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_SHARES = "require_shares"  # Need to provide key shares
    EXPIRED = "expired"  # Time-limited access has expired


@dataclass
class PolicyContext:
    """Context for policy evaluation."""
    user_id: int
    user_role: str
    file_id: int
    file_owner_id: int
    action: str  # "decrypt", "view", "delete", "share"
    request_time: datetime = None
    provided_shares: List[int] = None  # Share indices provided
    
    def __post_init__(self):
        if self.request_time is None:
            self.request_time = datetime.now(timezone.utc)
        if self.provided_shares is None:
            self.provided_shares = []


# ---------------------------------------------------------------------------
# Policy Model
# ---------------------------------------------------------------------------
class Policy(db.Model):
    """Access policy for a media file or global default."""
    __tablename__ = "policies"
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Scope: file-specific or global
    media_id = db.Column(db.Integer, db.ForeignKey("media_files.id"), nullable=True)
    is_global = db.Column(db.Boolean, default=False)
    
    # Policy configuration
    policy_type = db.Column(db.String(30), nullable=False, default=PolicyType.OWNER_ONLY.value)
    priority = db.Column(db.Integer, default=0)  # Higher = evaluated first
    
    # Policy parameters (JSON-like storage)
    # For SHARED: list of user IDs
    allowed_users = db.Column(db.Text, nullable=True)  # Comma-separated user IDs
    
    # For TIME_LIMITED: expiry timestamp
    expires_at = db.Column(db.DateTime, nullable=True)
    
    # For MULTI_PARTY: threshold
    required_approvals = db.Column(db.Integer, default=1)
    
    # Custom rule expression (for CUSTOM type)
    rule_expression = db.Column(db.Text, nullable=True)
    
    # Metadata
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    enabled = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f"<Policy {self.policy_type} media_id={self.media_id}>"
    
    def get_allowed_users(self) -> List[int]:
        """Parse allowed_users string into list of user IDs."""
        if not self.allowed_users:
            return []
        return [int(x.strip()) for x in self.allowed_users.split(",") if x.strip()]
    
    def set_allowed_users(self, user_ids: List[int]):
        """Set allowed_users from list of user IDs."""
        self.allowed_users = ",".join(str(uid) for uid in user_ids)


class PolicyLog(db.Model):
    """Audit log for policy evaluations."""
    __tablename__ = "policy_logs"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    media_id = db.Column(db.Integer, db.ForeignKey("media_files.id"), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    decision = db.Column(db.String(20), nullable=False)
    policy_id = db.Column(db.Integer, db.ForeignKey("policies.id"), nullable=True)
    reason = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<PolicyLog user={self.user_id} action={self.action} decision={self.decision}>"


# ---------------------------------------------------------------------------
# Policy Engine Functions
# ---------------------------------------------------------------------------

def evaluate_policy(context: PolicyContext) -> tuple[AccessDecision, str, Optional[int]]:
    """
    Evaluate access policies for a given context.
    
    Args:
        context: PolicyContext with request details
        
    Returns:
        Tuple of (decision, reason, policy_id)
    """
    # 1. Check admin override (highest priority global rule)
    if context.user_role == "admin":
        return AccessDecision.ALLOW, "Admin has full access", None
    
    # 2. Get file-specific policies
    file_policies = Policy.query.filter_by(
        media_id=context.file_id,
        enabled=True
    ).order_by(Policy.priority.desc()).all()
    
    # 3. Get global policies
    global_policies = Policy.query.filter_by(
        is_global=True,
        enabled=True
    ).order_by(Policy.priority.desc()).all()
    
    all_policies = file_policies + global_policies
    
    # 4. If no policies defined, use default (owner-only)
    if not all_policies:
        if context.user_id == context.file_owner_id:
            return AccessDecision.ALLOW, "Owner access (default policy)", None
        return AccessDecision.DENY, "Access denied - owner only (default)", None
    
    # 5. Evaluate each policy in priority order
    for policy in all_policies:
        decision, reason = _evaluate_single_policy(policy, context)
        if decision == AccessDecision.ALLOW:
            return decision, reason, policy.id
        if decision == AccessDecision.REQUIRE_SHARES:
            return decision, reason, policy.id
    
    # 6. No policy allowed access
    return AccessDecision.DENY, "No matching policy allowed access", None


def _evaluate_single_policy(policy: Policy, context: PolicyContext) -> tuple[AccessDecision, str]:
    """Evaluate a single policy against the context."""
    
    if policy.policy_type == PolicyType.OWNER_ONLY.value:
        if context.user_id == context.file_owner_id:
            return AccessDecision.ALLOW, "Owner access granted"
        return AccessDecision.DENY, "Not the file owner"
    
    elif policy.policy_type == PolicyType.ADMIN_OVERRIDE.value:
        if context.user_role == "admin":
            return AccessDecision.ALLOW, "Admin override"
        return AccessDecision.DENY, "Admin access only"
    
    elif policy.policy_type == PolicyType.SHARED.value:
        allowed = policy.get_allowed_users()
        if context.user_id in allowed or context.user_id == context.file_owner_id:
            return AccessDecision.ALLOW, "User in share list"
        return AccessDecision.DENY, "User not in share list"
    
    elif policy.policy_type == PolicyType.TIME_LIMITED.value:
        # Check if user is allowed (owner or shared)
        if context.user_id != context.file_owner_id:
            allowed = policy.get_allowed_users()
            if context.user_id not in allowed:
                return AccessDecision.DENY, "User not authorized"
        
        # Check expiry (handle both naive and aware datetimes)
        if policy.expires_at:
            expires_at = policy.expires_at
            request_time = context.request_time
            # Make both aware or both naive for comparison
            if expires_at.tzinfo is None and request_time.tzinfo is not None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            elif expires_at.tzinfo is not None and request_time.tzinfo is None:
                request_time = request_time.replace(tzinfo=timezone.utc)
            if request_time > expires_at:
                return AccessDecision.EXPIRED, "Access has expired"
        return AccessDecision.ALLOW, "Time-limited access valid"
    
    elif policy.policy_type == PolicyType.MULTI_PARTY.value:
        # Check if enough shares are provided
        if len(context.provided_shares) >= policy.required_approvals:
            return AccessDecision.ALLOW, f"Multi-party: {len(context.provided_shares)}/{policy.required_approvals} shares provided"
        return AccessDecision.REQUIRE_SHARES, f"Need {policy.required_approvals} shares, got {len(context.provided_shares)}"
    
    elif policy.policy_type == PolicyType.CUSTOM.value:
        # Evaluate custom rule expression (basic implementation)
        return _evaluate_custom_rule(policy.rule_expression, context)
    
    return AccessDecision.DENY, "Unknown policy type"


def _evaluate_custom_rule(expression: str, context: PolicyContext) -> tuple[AccessDecision, str]:
    """
    Evaluate a custom rule expression.
    
    Simple expression language:
    - "user.id == 5" → check user ID
    - "user.role == 'admin'" → check role
    - "file.owner_id == user.id" → ownership check
    - "action == 'view'" → action check
    """
    if not expression:
        return AccessDecision.DENY, "Empty custom rule"
    
    # Create evaluation context
    eval_vars = {
        "user_id": context.user_id,
        "user_role": context.user_role,
        "file_id": context.file_id,
        "file_owner_id": context.file_owner_id,
        "action": context.action,
        "is_owner": context.user_id == context.file_owner_id,
        "is_admin": context.user_role == "admin",
    }
    
    try:
        # Safe evaluation of simple expressions
        # Replace variable references
        expr = expression
        for var, val in eval_vars.items():
            if isinstance(val, str):
                expr = expr.replace(var, f"'{val}'")
            elif isinstance(val, bool):
                expr = expr.replace(var, str(val))
            else:
                expr = expr.replace(var, str(val))
        
        # Only allow safe operations
        allowed_chars = set("0123456789 ==!<>&|()\"'truefalseandornot")
        if not set(expr.lower().replace(" ", "")).issubset(allowed_chars):
            return AccessDecision.DENY, "Invalid custom rule expression"
        
        result = eval(expr, {"__builtins__": {}}, {})
        if result:
            return AccessDecision.ALLOW, f"Custom rule passed: {expression}"
        return AccessDecision.DENY, f"Custom rule failed: {expression}"
    
    except Exception as e:
        return AccessDecision.DENY, f"Custom rule error: {str(e)}"


def log_policy_decision(context: PolicyContext, decision: AccessDecision, 
                        reason: str, policy_id: Optional[int] = None):
    """Log a policy evaluation result."""
    log = PolicyLog(
        user_id=context.user_id,
        media_id=context.file_id,
        action=context.action,
        decision=decision.value,
        policy_id=policy_id,
        reason=reason
    )
    db.session.add(log)
    db.session.commit()


def check_access(user_id: int, user_role: str, file_id: int, 
                 file_owner_id: int, action: str = "decrypt",
                 provided_shares: List[int] = None) -> tuple[bool, str]:
    """
    High-level access check function.
    
    Args:
        user_id: Requesting user's ID
        user_role: User's role (admin/user)
        file_id: Target file ID
        file_owner_id: File owner's ID
        action: Action being attempted
        provided_shares: Optional list of share indices
        
    Returns:
        Tuple of (allowed: bool, reason: str)
    """
    context = PolicyContext(
        user_id=user_id,
        user_role=user_role,
        file_id=file_id,
        file_owner_id=file_owner_id,
        action=action,
        provided_shares=provided_shares or []
    )
    
    decision, reason, policy_id = evaluate_policy(context)
    
    # Log the decision
    log_policy_decision(context, decision, reason, policy_id)
    
    allowed = decision == AccessDecision.ALLOW
    return allowed, reason


# ---------------------------------------------------------------------------
# Policy Management Functions
# ---------------------------------------------------------------------------

def create_policy(media_id: Optional[int], policy_type: PolicyType, 
                  created_by: int, **kwargs) -> Policy:
    """
    Create a new policy.
    
    Args:
        media_id: File ID (None for global policy)
        policy_type: Type of policy
        created_by: User ID creating the policy
        **kwargs: Additional policy parameters
        
    Returns:
        The created Policy
    """
    policy = Policy(
        media_id=media_id,
        is_global=(media_id is None),
        policy_type=policy_type.value,
        created_by=created_by,
        priority=kwargs.get("priority", 0),
        expires_at=kwargs.get("expires_at"),
        required_approvals=kwargs.get("required_approvals", 1),
        rule_expression=kwargs.get("rule_expression"),
        enabled=kwargs.get("enabled", True)
    )
    
    if "allowed_users" in kwargs:
        policy.set_allowed_users(kwargs["allowed_users"])
    
    db.session.add(policy)
    db.session.commit()
    return policy


def update_policy(policy_id: int, **kwargs) -> Optional[Policy]:
    """Update an existing policy."""
    policy = Policy.query.get(policy_id)
    if not policy:
        return None
    
    for key, value in kwargs.items():
        if key == "allowed_users":
            policy.set_allowed_users(value)
        elif hasattr(policy, key):
            setattr(policy, key, value)
    
    db.session.commit()
    return policy


def delete_policy(policy_id: int) -> bool:
    """Delete a policy."""
    policy = Policy.query.get(policy_id)
    if not policy:
        return False
    
    db.session.delete(policy)
    db.session.commit()
    return True


def get_file_policies(media_id: int) -> List[Policy]:
    """Get all policies for a specific file."""
    return Policy.query.filter_by(media_id=media_id, enabled=True).all()


def get_global_policies() -> List[Policy]:
    """Get all global policies."""
    return Policy.query.filter_by(is_global=True, enabled=True).all()


def share_file(media_id: int, owner_id: int, target_user_ids: List[int],
               expires_at: Optional[datetime] = None) -> Policy:
    """
    Share a file with specific users.
    
    Creates or updates a SHARED or TIME_LIMITED policy.
    """
    policy_type = PolicyType.TIME_LIMITED if expires_at else PolicyType.SHARED
    
    # Check for existing share policy
    existing = Policy.query.filter_by(
        media_id=media_id,
        policy_type=policy_type.value,
        enabled=True
    ).first()
    
    if existing:
        # Update existing policy
        current_users = set(existing.get_allowed_users())
        current_users.update(target_user_ids)
        existing.set_allowed_users(list(current_users))
        if expires_at:
            existing.expires_at = expires_at
        db.session.commit()
        return existing
    
    # Create new policy
    return create_policy(
        media_id=media_id,
        policy_type=policy_type,
        created_by=owner_id,
        allowed_users=target_user_ids,
        expires_at=expires_at
    )


def revoke_share(media_id: int, target_user_id: int) -> bool:
    """Remove a user from the share list."""
    policies = Policy.query.filter(
        Policy.media_id == media_id,
        Policy.policy_type.in_([PolicyType.SHARED.value, PolicyType.TIME_LIMITED.value]),
        Policy.enabled == True
    ).all()
    
    for policy in policies:
        users = policy.get_allowed_users()
        if target_user_id in users:
            users.remove(target_user_id)
            policy.set_allowed_users(users)
    
    db.session.commit()
    return True
