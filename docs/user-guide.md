# SecureMedia — User Guide

## Overview
SecureMedia is a web-based platform for **encrypting**, **watermarking**, and securely managing audio & video files. Every file you upload is automatically:

1. **Forensically watermarked** (spread-spectrum for audio, DWT for video)
2. **Encrypted** with AES-256-GCM (key wrapped with Fernet)
3. **Policy-controlled** via RBAC + ABAC engine

---

## Getting Started

### 1. Register
- Navigate to `/auth/register`
- Fill in **username**, **email**, and **password** (min 8 characters)
- Click **Create Account**
- You'll be redirected to the login page

### 2. Log In
- Navigate to `/auth/login`
- Enter your email and password
- Optionally check **Remember me** for persistent sessions
- Click **Sign In**

### 3. Dashboard
After login you land on the dashboard (`/`), which shows:
- **Stats cards**: Total files, storage used, watermarked count, encrypted count, **shared with me count**
- **File table**: All your encrypted files with download, detail, and delete actions
- **Shared with Me section**: Files that other users have shared with you, with owner info and download button
- An **Upload** button to add new files

---

## Uploading Files

1. Click **Upload** in the navigation bar or dashboard
2. **Drag & drop** a file onto the upload area, or click to browse
3. Supported formats: `mp3`, `wav`, `ogg`, `flac`, `aac`, `mp4`, `avi`, `mkv`, `mov`, `webm`
4. Maximum file size: **500 MB**
5. Click **Encrypt & Upload**
6. The system will:
   - Embed a forensic watermark (payload: your user ID + timestamp)
   - Encrypt the file with AES-256-GCM
   - Wrap the encryption key with Fernet
   - Store the encrypted file and metadata
7. A **step-by-step spinner** shows progress: Preparing file → Embedding watermark → Encrypting with AES-256-GCM → Wrapping key with Fernet → Storing KMS keys → Uploading securely → Almost done
8. You'll see a success message and return to the dashboard

---

## Downloading & Decrypting

1. From the dashboard, click the **download icon** (⬇) next to a file
2. The system will:
   - Check **access policies** (RBAC/ABAC engine — owner, admin, or shared user)
   - Decrypt the file using the stored wrapped key
   - Verify the embedded watermark
   - Stream the original file to your browser
3. If access is denied by policy, you'll see an error message

---

## Downloading Encrypted Files

You can also download the **raw encrypted ciphertext** without decryption:

1. From the file detail page, click **Download Encrypted**
2. The system delivers the `.enc` file as-is (no decryption)
3. **Use cases:** offline backup, forensic analysis, transfer to another system
4. Access is controlled by the same policy engine (owner, admin, or shared user)

---

## Verifying Encryption

To prove a file is truly encrypted, use the **Verify Encryption** page:

1. From the file detail page or dashboard, click **Verify Encryption**
2. The system runs **10 verification checks**:
   - ✅ File exists on disk
   - ✅ Magic bytes analysis (not a known plaintext format)
   - ✅ Shannon entropy calculation (high entropy = encrypted)
   - ✅ SHA-256 hash of ciphertext
   - ✅ Fernet key unwrap test
   - ✅ AES key length (32 bytes = AES-256)
   - ✅ KMS record exists
   - ✅ Watermark info present
   - ✅ Database status check
   - ✅ Overall verdict
3. Results shown with a **verdict banner** (green PASS / red FAIL), entropy bar, and hex preview

---

## Sharing Files

You can share your files with other registered users:

### Sharing a File
1. Navigate to a file's **detail page** (`/file/<id>`)
2. In the **Sharing** card on the right sidebar, use the multi-select dropdown to choose users
3. Click **Share File**
4. Selected users will see the file in their "Shared with Me" dashboard section
5. An audit log entry is created for each share

### Revoking Access
1. On the file detail page, find the user in the **Currently Shared With** list
2. Click the **Revoke** button next to their name
3. Access is removed instantly — the user can no longer see or download the file

### What Shared Users Can Do
- View the file detail page (with an info banner: "This file was shared with you by [owner]")
- **Download** the decrypted file
- **Download Encrypted** (raw ciphertext)
- They **cannot** delete, re-share, or modify the file

---

## File Detail Page

Click a file name or the **info icon** on the dashboard to see:
- **File metadata**: name, size, MIME type, upload date
- **Watermark info**: watermark ID and payload
- **Security details**: encryption algorithm, key wrapping, watermark status
- **File activity log**: upload, download, delete, and share events
- **Sharing card** (owners only): current shares, share form, revoke buttons
- **Actions**: download, download encrypted, verify encryption, delete (owners); download and download encrypted only (shared users)
- **Info banner** (shared users): "This file was shared with you by [owner]"

---

## Profile Page

Click your **username** in the navigation bar to view:
- Account information (username, email, role)
- Storage statistics (file count, total size)
- Recent activity log (uploads, downloads, logins)

---

## Admin Panel (Admin Users Only)

Admins have access to additional management features via the **Admin** dropdown:

### All Files (`/admin/files`)
- View every file in the system regardless of owner
- Download or delete any file

### Key Management (`/admin/keys`)
- View all encryption key records
- See key status (active/revoked), share count, threshold
- **Revoke keys** (permanently prevents decryption)
- **Split keys** using Shamir's Secret Sharing (configurable n-of-k threshold)

### Policy Management (`/admin/policies`)
- Create, enable/disable, and delete access policies
- **Policy types**:
  - `owner_only` — Only file owner can decrypt
  - `admin_override` — Admins can always decrypt
  - `shared` — Specific users can decrypt
  - `time_limited` — Access expires at a set date/time
  - `multi_party` — Requires multiple approvals
  - `custom` — Custom rule expression

### User Management (`/admin/users`)
- View all registered users
- Grant or revoke admin privileges

### Audit Logs (`/admin/audit`)
- **General logs**: Every upload, download, delete, login/logout event
- **Policy decision logs**: Every access check with allow/deny decisions
- Paginated views with timestamps and details

---

## REST API

All endpoints require authentication (session cookie).

### List Files
```
GET /api/files
→ 200 [{ "id", "filename", "size", "mime_type", "watermark_id", "created_at" }]
```

### File Detail
```
GET /api/files/<id>
→ 200 { "id", "filename", "size", "mime_type", "status", "watermark_id", "watermark_payload", "created_at" }
→ 404 { "error": "File not found" }
→ 403 { "error": "Forbidden" }
```

### Upload File
```
POST /api/upload  (multipart/form-data, field: "file")
→ 201 { "id", "filename", "size", "watermark_id" }
→ 400 { "error": "No file selected" | "File type not allowed" }
```

### Delete File
```
DELETE /api/files/<id>
→ 200 { "message": "File deleted" }
→ 404 { "error": "File not found" }
→ 403 { "error": "Forbidden" }
```

### Admin API
```
GET  /admin/api/keys                → 200 [key records]
GET  /admin/api/keys/<media_id>     → 200 key detail | 404
POST /admin/api/check-access        → 200 { "allowed", "reason" }
```

---

## Security Features

| Feature | Implementation |
|---|---|
| Encryption | AES-256-GCM with random nonce per file |
| Key Management | Fernet key wrapping + Shamir's Secret Sharing |
| Watermarking | Spread-spectrum (audio), DWT (video) |
| Authentication | Flask-Login with bcrypt password hashing |
| CSRF Protection | Flask-WTF CSRFProtect on all POST forms |
| Access Control | RBAC + ABAC policy engine with 6 policy types |
| File Sharing | Policy-based sharing with instant revoke |
| Encryption Verification | 10-point checker (entropy, hash, keys, KMS) |
| Audit Trail | Every action logged with user, timestamp, result |
| Error Handling | Custom 403, 404, 500 error pages |

---

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables (optional)
export FERNET_MASTER_KEY="your-base64-key"
export SECRET_KEY="your-secret-key"

# Create admin user
flask seed-admin

# Run development server
python run.py
```

The app will start at `http://127.0.0.1:5000`.
