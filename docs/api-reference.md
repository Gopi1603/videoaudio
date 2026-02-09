# SecureMedia — API Reference

## Overview
SecureMedia exposes both traditional web routes (HTML responses) and a RESTful JSON API.
All endpoints require authentication unless noted otherwise.

**Base URL:** `http://localhost:5000` (dev) or `https://yourdomain.com` (prod)

---

## Authentication Endpoints

### POST `/auth/register`
Create a new user account.

**Content-Type:** `application/x-www-form-urlencoded`

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `username` | string | ✅ | 3–80 characters, unique |
| `email` | string | ✅ | Valid email, unique |
| `password` | string | ✅ | 8–128 characters |
| `confirm_password` | string | ✅ | Must match password |

**Responses:**
- `302` → Redirect to `/auth/login` on success
- `200` → Re-render form with validation errors

**Audit:** Creates `register` audit log entry.

---

### POST `/auth/login`
Authenticate and create a session.

| Field | Type | Required |
|-------|------|----------|
| `email` | string | ✅ |
| `password` | string | ✅ |
| `remember` | boolean | ❌ |

**Responses:**
- `302` → Redirect to `/` (dashboard) on success
- `200` → Re-render form with "Invalid email or password"

**Audit:** Creates `login` (success/failure) audit log entry.

---

### GET `/auth/logout`
End the current session.

**Auth:** Required  
**Response:** `302` → Redirect to `/auth/login`  
**Audit:** Creates `logout` audit log entry.

---

## Media Endpoints (Web)

### GET `/`
Dashboard — list current user's encrypted files and files shared with them.

**Auth:** Required  
**Response:** `200` HTML with file table, stats cards (total, storage, watermarked, encrypted, shared with me), and "Shared with Me" section.

---

### GET/POST `/upload`
Upload and encrypt a media file.

**Auth:** Required  
**Method:** `POST` (multipart/form-data)

| Field | Type | Required |
|-------|------|----------|
| `file` | File | ✅ |

**Allowed Extensions:** `mp3`, `wav`, `ogg`, `flac`, `aac`, `mp4`, `avi`, `mkv`, `mov`, `webm`  
**Max Size:** 500 MB

**Processing Pipeline:**
1. Validate file extension
2. Generate watermark payload (`uid:<id>|ts:<timestamp>`)
3. Embed watermark (spread-spectrum / DWT)
4. Encrypt with AES-256-GCM
5. Wrap key with Fernet
6. Store encrypted file + metadata

**Responses:**
- `302` → Redirect to dashboard with success flash
- `200` → Re-render form with error message

**Audit:** Creates `upload` audit log with file size, encryption time, watermark ID.

---

### GET `/download/<file_id>`
Decrypt and download a file.

**Auth:** Required (owner, admin, or shared user via policy engine)

**Processing Pipeline:**
1. Check ownership / admin role
2. Retrieve and unwrap AES key
3. Decrypt file with AES-256-GCM
4. Extract and verify watermark
5. Stream decrypted file

**Responses:**
- `200` → File download (as attachment)
- `403` → Not authorized
- `404` → File not found or deleted

**Audit:** Creates `download` audit log with decryption time, watermark match.

---

### POST `/delete/<file_id>`
Soft-delete a file.

**Auth:** Required (owner or admin)

**Responses:**
- `302` → Redirect to dashboard with "File deleted" flash
- `403` → Not authorized
- `404` → File not found

**Audit:** Creates `delete` audit log.

---

### GET `/file/<file_id>`
View file details page.

**Auth:** Required (owner, admin, or shared user)

**Response:** `200` HTML with:
- File metadata (name, size, date, MIME type)
- Encryption info (AES-256-GCM, key status)
- Watermark info (payload, watermark ID)
- Audit log history for this file
- **Sharing card** (owner only): current shares, share form with user multi-select, revoke buttons
- **Contextual actions**: owner sees all buttons; shared users see Download & Download Encrypted only
- **Info banner**: shared users see "This file was shared with you by [owner]"

---

### POST `/share/<file_id>`
Share a file with one or more users via the policy engine.

**Auth:** Required (file owner only)

| Field | Type | Required |
|-------|------|----------|
| `user_ids` | list[integer] | ✅ |

**Processing:**
1. Validate current user is file owner
2. Create SHARED policies for each selected user via `share_file()`
3. Log share event to audit trail

**Responses:**
- `302` → Redirect to `/file/<file_id>` with success flash
- `403` → Not the file owner
- `404` → File not found

**Audit:** Creates `share` audit log with shared user IDs.

---

### POST `/revoke/<file_id>/<user_id>`
Revoke a user's shared access to a file.

**Auth:** Required (file owner only)

**Processing:**
1. Validate current user is file owner
2. Remove SHARED policy for the specified user via `revoke_share()`
3. Log revoke event to audit trail

**Responses:**
- `302` → Redirect to `/file/<file_id>` with success flash
- `403` → Not the file owner
- `404` → File not found

**Audit:** Creates `revoke_share` audit log.

---

### GET `/verify/<file_id>`
Verify that a file is truly encrypted with a 10-point check.

**Auth:** Required (owner or admin)

**Verification Checks:**
1. File exists on disk
2. Magic bytes analysis (not a known plaintext format)
3. Shannon entropy calculation (high entropy = encrypted)
4. SHA-256 hash of ciphertext
5. Fernet key unwrap test
6. AES key length verification (32 bytes = AES-256)
7. KMS record exists
8. Watermark info present
9. Database status check
10. Overall verdict (PASS if ≥8 checks pass)

**Response:** `200` HTML with:
- Verdict banner (green PASS / red FAIL)
- Individual check results with icons
- Entropy bar visualization
- Hex preview of first 64 bytes
- SHA-256 hash display

---

### GET `/download-encrypted/<file_id>`
Download the raw encrypted ciphertext without decryption.

**Auth:** Required (owner, admin, or shared user via policy engine)

**Processing:**
1. Check access via `check_access()` policy engine
2. Read raw `.enc` file from disk
3. Serve as `application/octet-stream` with `.enc` extension

**Responses:**
- `200` → Raw ciphertext file download
- `403` → Not authorized (policy denied)
- `404` → File not found

**Use Cases:**
- Offline backup of encrypted data
- Forensic analysis of ciphertext
- Transfer encrypted files to another system

---

### GET `/profile`
View current user's profile.

**Auth:** Required  
**Response:** `200` HTML with user info, stats, recent activity.

---

## REST API Endpoints (JSON)

### GET `/api/files`
List current user's files as JSON.

**Auth:** Required

**Response:** `200`
```json
[
  {
    "id": 1,
    "original_filename": "lecture.mp3",
    "file_size": 5242880,
    "mime_type": "audio/mpeg",
    "status": "encrypted",
    "created_at": "2026-01-15T10:30:00Z",
    "watermark_id": "a1b2c3d4"
  }
]
```

---

### GET `/api/files/<file_id>`
Get details for a specific file.

**Auth:** Required (owner or admin)

**Response:** `200`
```json
{
  "id": 1,
  "original_filename": "lecture.mp3",
  "file_size": 5242880,
  "mime_type": "audio/mpeg",
  "status": "encrypted",
  "created_at": "2026-01-15T10:30:00Z",
  "watermark_id": "a1b2c3d4",
  "watermark_payload": "uid:1|ts:1705312200"
}
```

**Errors:**
- `403` → Not authorized
- `404` → File not found

---

### POST `/api/upload`
Upload a file via API (JSON response).

**Auth:** Required  
**Content-Type:** `multipart/form-data`

| Field | Type | Required |
|-------|------|----------|
| `file` | File | ✅ |

**Response:** `201`
```json
{
  "id": 5,
  "filename": "lecture.mp3",
  "status": "encrypted",
  "message": "File uploaded and encrypted successfully"
}
```

**Errors:**
- `400` → No file or invalid extension

---

### DELETE `/api/files/<file_id>`
Delete a file via API.

**Auth:** Required (owner or admin)

**Response:** `200`
```json
{
  "message": "File deleted",
  "id": 1
}
```

**Errors:**
- `403` → Not authorized
- `404` → File not found

---

## Admin API Endpoints

All admin endpoints require the `admin` role. Non-admin users receive a redirect or `403`.

### GET `/admin/api/keys`
List all encryption key records.

**Response:** `200` JSON array of key records.

---

### POST `/admin/keys/<media_id>/revoke`
Revoke an encryption key (makes file permanently undecryptable).

**Response:** `302` → Redirect to `/admin/keys` with flash message.

---

### POST `/admin/keys/<media_id>/rotate`
Rotate (re-encrypt) a file's key.

**Response:** `302` → Redirect to `/admin/keys` with flash message.

---

### POST `/admin/users/<user_id>/toggle-admin`
Toggle a user's admin status.

**Response:** `302` → Redirect to `/admin/users`.

---

### POST `/admin/policies/create`
Create a new access policy.

| Field | Type | Required |
|-------|------|----------|
| `media_id` | integer | ✅ |
| `policy_type` | string | ✅ |

**Response:** `302` → Redirect to `/admin/policies`.

---

## Health Check

### GET `/health`
Docker/load-balancer health probe.

**Auth:** Not required

**Response:** `200`
```json
{
  "status": "healthy",
  "db": "ok"
}
```

**Unhealthy:** `503`
```json
{
  "status": "unhealthy",
  "db": "error message"
}
```

---

## Error Responses

All error pages render both HTML (browser) and JSON (API clients based on `Accept` header).

| Code | Meaning | JSON Response |
|------|---------|---------------|
| `400` | Bad Request | `{"error": "Bad request"}` |
| `401` | Unauthorized | Redirect to `/auth/login` |
| `403` | Forbidden | `{"error": "Forbidden"}` |
| `404` | Not Found | `{"error": "Not found"}` |
| `500` | Server Error | `{"error": "Internal server error"}` |

---

## CSRF Protection

All POST/PUT/DELETE requests via forms require a CSRF token:
```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

**Disabled for:** Testing configuration (`WTF_CSRF_ENABLED = False`)  
**API clients:** CSRF is enforced; include the token from the session cookie or use `X-CSRFToken` header.
