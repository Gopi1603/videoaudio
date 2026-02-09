# Phase 2 — Prototype Report

## What Was Built
A minimal Flask application implementing the full upload → encrypt → store → decrypt → download pipeline, with user authentication (Flask-Login) and two roles (Admin, Standard User).

## Components Delivered

| Component | Description |
|-----------|-------------|
| **App Factory** (`app/__init__.py`) | Creates Flask app, initialises SQLAlchemy + Flask-Login, registers blueprints. |
| **Models** (`app/models.py`) | `User` (roles: admin/user), `MediaFile` (encrypted file metadata + Fernet-wrapped key), `AuditLog`. |
| **Auth Blueprint** (`app/auth/`) | Register, login, logout with WTForms validation and audit logging. |
| **Encryption Module** (`app/encryption.py`) | AES-256-GCM for media encryption; Fernet master key wraps per-file AES keys; high-level `encrypt_file` / `decrypt_file` helpers. |
| **Media Blueprint** (`app/media/`) | Upload (encrypt & store), download (decrypt & stream), delete, admin file listing. |
| **Templates** | Dark-themed Bootstrap 5 UI: login, register, dashboard, upload, admin files. |
| **Tests** (`tests/`) | 16 tests — encryption roundtrips (small/large/empty/tampered), key wrap/unwrap, auth flows, upload/download/delete via test client. |

## Encryption Scheme
1. On upload, a fresh 256-bit AES key is generated per file.
2. Media bytes are encrypted with **AES-GCM** (12-byte nonce prepended to ciphertext+tag).
3. The per-file AES key is **wrapped with Fernet** (a master key) and stored in the database.
4. On download, the Fernet token is unwrapped to recover the AES key, then AES-GCM decrypts the file.
5. If ciphertext is tampered, AES-GCM's authentication tag fails and decryption is refused.

## Test Results
All 16 tests pass (pytest):
- Key generation produces 32-byte keys.
- Wrap/unwrap roundtrip is lossless.
- Encrypt→decrypt roundtrip works for 0 B, small, and 5 MB payloads.
- Wrong key and tampered ciphertext both raise exceptions (integrity verified).
- Auth flows (register, login, logout, duplicate rejection, wrong password) work correctly.
- Upload creates an encrypted file on disk and a DB record; download returns the original bytes.

## Limitations & Next Steps
- **No watermarking yet** — watermark embedding comes in Phase 3.
- **Basic ownership check only** — full Policy Engine deferred to Phase 4.
- **KMS is in-DB** — Shamir's Secret Sharing and key rotation deferred to Phase 4.
- **No CSRF on file delete form** — can be tightened in Phase 5.
- **Fernet master key** is auto-generated in dev; must be injected via env var in production.
- **Streaming encryption** for very large files (>500 MB) is not implemented; current approach loads the file into memory.
