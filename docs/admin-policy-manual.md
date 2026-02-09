# SecureMedia — Admin & Policy Manual

## Table of Contents
1. [Admin Role Overview](#admin-role-overview)
2. [Accessing the Admin Panel](#accessing-the-admin-panel)
3. [User Management](#user-management)
4. [File Management](#file-management)
5. [Key Management](#key-management)
6. [Policy Engine](#policy-engine)
7. [Audit Logs](#audit-logs)
8. [Security Best Practices](#security-best-practices)

---

## Admin Role Overview

Admins have elevated privileges to manage the entire SecureMedia platform:

| Capability | Admin | Standard User |
|------------|:-----:|:-------------:|
| Upload / download own files | ✅ | ✅ |
| View own file details | ✅ | ✅ |
| Delete own files | ✅ | ✅ |
| View/download ANY user's files | ✅ | ❌ |
| Manage users (promote/demote) | ✅ | ❌ |
| View/revoke encryption keys | ✅ | ❌ |
| Create/edit access policies | ✅ | ❌ |
| View audit logs | ✅ | ❌ |
| Access admin API endpoints | ✅ | ❌ |

---

## Accessing the Admin Panel

### Creating the First Admin
```bash
# Via CLI command
flask seed-admin
# Creates: admin@securemedia.local / Admin@1234

# Or in Docker
docker compose exec web flask seed-admin
```

### Admin Routes
All admin pages are under `/admin/`:

| Route | Purpose |
|-------|---------|
| `/admin/files` | View all files in the system |
| `/admin/keys` | Key management dashboard |
| `/admin/users` | User management |
| `/admin/policies` | Policy management |
| `/admin/audit` | Audit log viewer |

Non-admin users attempting to access these routes are redirected to the dashboard with an "Admin access required" flash message.

---

## User Management

### Route: `/admin/users`

Displays all registered users with their roles, registration dates, and file counts.

**Actions:**
- **Toggle Admin**: Click the toggle button to promote a user to admin or demote back to standard user
  - Route: `POST /admin/users/<id>/toggle-admin`
  - Protected by `@admin_required` decorator

**Important:** The system requires at least one admin account. Be cautious when demoting admins.

---

## File Management

### Route: `/admin/files`

Shows ALL files in the system regardless of owner, including:
- Original filename and owner
- File size and upload date
- Encryption status
- Watermark ID

**Admin Actions:**
- View any file's detail page (`/file/<id>`)
- Download any file (bypasses owner-only policy)
- Delete any file
- Revoke encryption keys

---

## Key Management

### Route: `/admin/keys`

The Key Management Service (KMS) provides:

### Key Lifecycle
1. **Generation**: A fresh AES-256 key is created for each uploaded file
2. **Wrapping**: Key is encrypted with the Fernet master key before DB storage
3. **Storage**: Wrapped key stored in `media_files.encrypted_key` column
4. **Splitting** (optional): Key split into Shamir shares for multi-party access
5. **Retrieval**: Key unwrapped on download (after policy check)
6. **Revocation**: Key permanently removed, making file undecryptable

### Shamir's Secret Sharing
Keys can be split into `n` shares with threshold `k`:
- Uses GF(257) finite field arithmetic
- Minimum threshold: `k ≥ 2`
- Maximum shares: `n ≤ 255`
- Any `k` shares can reconstruct the original key

### Key Revocation
- **Route**: `POST /admin/keys/<media_id>/revoke`
- Permanently marks the key as revoked
- The file becomes **permanently undecryptable**
- An audit log entry is created
- This action is **irreversible**

### Key Rotation
- **Route**: `POST /admin/keys/<media_id>/rotate`
- Generates a new AES key
- Re-encrypts the file with the new key
- Revokes the old key record
- Creates a new key record

---

## Policy Engine

### Route: `/admin/policies`

The policy engine supports 6 policy types for fine-grained access control:

### Policy Types

| Type | Description | Configuration |
|------|-------------|---------------|
| `OWNER_ONLY` | Only the file owner can access | Default for all files |
| `ADMIN_OVERRIDE` | Admins can access any file | Always active |
| `SHARED` | Specific users can access | Requires `shared_with` user list |
| `TIME_LIMITED` | Access expires after a date | Requires `expires_at` datetime |
| `MULTI_PARTY` | Multiple approvals needed | Requires `threshold` + approvers |
| `CUSTOM` | Custom rule evaluation | Requires `rule_definition` JSON |

### Creating a Policy
```
POST /admin/policies/create
Form fields:
  - media_id: ID of the file
  - policy_type: One of the policy types above
  - (Additional fields based on policy type)
```

### Policy Evaluation Order
1. Check if user is **admin** → `ALLOW` (admin override)
2. Check if user is **file owner** → `ALLOW` (owner access)
3. Check `TIME_LIMITED` policies → `DENY` if expired
4. Check `SHARED` policies → `ALLOW` if user in share list
5. Check `MULTI_PARTY` policies → `REQUIRE_SHARES` if threshold not met
6. Default → `DENY`

### Policy Logging
Every policy evaluation is logged to `policy_logs` table:
- User ID, file ID, policy ID
- Decision (`ALLOW` / `DENY` / `REQUIRE_SHARES`)
- Timestamp and context details

---

## Audit Logs

### Route: `/admin/audit`

All significant actions are logged to the `audit_logs` table:

### Logged Events
| Action | Trigger | Details Captured |
|--------|---------|-----------------|
| `register` | New user signs up | User ID |
| `login` | Successful authentication | User ID, result |
| `login` (failure) | Failed authentication | User ID, result=failure |
| `logout` | User logs out | User ID |
| `upload` | File uploaded | Media ID, file size, encryption time, watermark ID |
| `download` | File downloaded | Media ID, decryption time, watermark match |
| `delete` | File deleted | Media ID |
| `key_revoke` | Admin revokes a key | Media ID, admin username |
| `key_rotate` | Admin rotates a key | Media ID, admin username |
| `policy_create` | New policy created | Policy ID, type |
| `policy_update` | Policy modified | Policy ID, changes |
| `share` | File shared with user | Media ID, target user |

### Audit Log Fields
- **user_id**: Who performed the action
- **action**: Action type (see above)
- **media_id**: Related file (if applicable)
- **result**: `"success"` or `"failure"`
- **detail**: Structured text with metrics
- **timestamp**: UTC timestamp

### Compliance Notes
- Audit logs are **immutable** — no delete/update operations
- All failed access attempts are logged
- Logs support FERPA compliance requirements
- Recommended: Export logs periodically for long-term retention

---

## Security Best Practices

### For Admins
1. **Change default credentials** immediately after first login
2. **Use strong passwords** (min 12 characters, mixed case + symbols)
3. **Review audit logs** weekly for suspicious activity
4. **Revoke keys** promptly when files should no longer be accessible
5. **Limit admin accounts** — only grant admin to trusted personnel
6. **Monitor failed logins** — repeated failures may indicate brute-force attempts

### Environment Security
1. **Never commit `.env`** to version control
2. **Rotate `SECRET_KEY`** and `FERNET_MASTER_KEY` periodically
3. **Use HTTPS** in production (Nginx + Let's Encrypt)
4. **Enable rate limiting** on auth and API endpoints
5. **Keep dependencies updated** — run `pip audit` periodically
6. **Back up the database** and `FERNET_MASTER_KEY` together — losing the key means losing all encrypted files

### Key Management Security
- The `FERNET_MASTER_KEY` is the **root of trust** — protect it above all else
- In production, use a secrets manager (AWS Secrets Manager, HashiCorp Vault)
- If the master key is compromised, all file keys can be unwrapped
- Key revocation is permanent and cannot be undone
