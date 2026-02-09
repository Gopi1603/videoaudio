# API Endpoints — Phase 2 Prototype

## Authentication (`/auth`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET/POST | `/auth/register` | No | Show registration form / create account. |
| GET/POST | `/auth/login` | No | Show login form / authenticate user. |
| GET | `/auth/logout` | Yes | Log out current session. |

### POST `/auth/register`
**Form fields:** `username`, `email`, `password`, `confirm_password`
**Success:** Redirect to `/auth/login` with flash message.
**Errors:** Re-render form with validation messages (duplicate email/username, weak password).

### POST `/auth/login`
**Form fields:** `email`, `password`, `remember` (checkbox)
**Success:** Redirect to `/` (dashboard).
**Errors:** Flash "Invalid email or password."

---

## Media (`/`)

| Method | Path | Auth | Role | Description |
|--------|------|------|------|-------------|
| GET | `/` | Yes | Any | Dashboard — list user's encrypted files. |
| GET/POST | `/upload` | Yes | Any | Show upload form / encrypt & store file. |
| GET | `/download/<file_id>` | Yes | Owner or Admin | Decrypt and stream the file. |
| POST | `/delete/<file_id>` | Yes | Owner or Admin | Soft-delete file (remove from disk, mark deleted). |
| GET | `/admin/files` | Yes | Admin | List all files in the system. |

### POST `/upload`
**Multipart field:** `file` (audio/video, max 500 MB)
**Allowed extensions:** mp3, wav, ogg, flac, aac, mp4, avi, mkv, mov, webm
**Flow:** Save temp → AES-GCM encrypt → store `.enc` file → wrap key with Fernet → save to DB.
**Success:** Redirect to dashboard with flash.

### GET `/download/<file_id>`
**Flow:** Check ownership/admin → unwrap key → AES-GCM decrypt to temp → `send_file`.
**403:** If user is not the owner and not an admin.
**404:** If file doesn't exist or is deleted.

---

## How to Run

```bash
pip install -r requirements.txt
python run.py                     # Starts dev server on http://127.0.0.1:5000
flask --app run:app seed-admin    # Create default admin account
```

**Default admin credentials (dev only):** `admin@securemedia.local` / `Admin@1234`
