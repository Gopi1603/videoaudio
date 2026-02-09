# Tech Stack Decision Log

## Backend
- **Framework**: Flask (Python)
  - Rationale: lightweight, easy to scaffold, fits PRD.
- **Crypto**: `cryptography` library
  - AES-GCM for media encryption
  - Fernet for key wrapping/metadata encryption
  - PBKDF2HMAC for key derivation (if needed)

## Auth & Security
- **Auth**: Flask-Login or JWT (to be confirmed in Phase 2)
- **Password Hashing**: bcrypt or argon2

## Watermarking
- **Audio**: PyDub / librosa (selection in Phase 3)
- **Video**: OpenCV + ffmpeg

## Storage
- **Dev**: Local filesystem
- **Prod**: Object storage (S3-compatible) with encryption at rest

## Data Store
- **Dev**: SQLite
- **Prod**: PostgreSQL

## Logging & Observability
- **Logging**: Python logging + structured JSON logs
- **Audit**: Database table for audit logs

## Dev Tooling
- **Environment**: Anaconda-compatible Python
- **Testing**: pytest

## Open Questions
- ~~RBAC framework: custom vs Oso/Casbin.~~ → **Resolved:** Custom RBAC+ABAC policy engine with 6 policy types + file sharing
- ~~Key splitting library for Shamir's Secret Sharing.~~ → **Resolved:** Custom GF(257) implementation in `app/kms.py`

## Additional Features (Added Post-Planning)
- **Policy-Based File Sharing**: Share/revoke files with other users via SHARED policies
- **Encryption Verification**: 10-point checker (entropy, magic bytes, SHA-256, KMS, Fernet, AES key)
- **Download Encrypted**: Serve raw AES-GCM ciphertext for offline storage/forensic analysis
- **Step-by-Step Upload Spinner**: Animated progress through pipeline stages
- **Admin Auto-Create**: Default admin account created on app startup
- **136 Automated Tests**: Full coverage across all modules
