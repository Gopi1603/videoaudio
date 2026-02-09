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
- RBAC framework: custom vs Oso/Casbin.
- Key splitting library for Shamir’s Secret Sharing.
