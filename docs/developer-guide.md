# SecureMedia — Developer Guide

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Local Development Setup](#local-development-setup)
4. [Docker Development](#docker-development)
5. [Configuration](#configuration)
6. [Database Models](#database-models)
7. [Module Reference](#module-reference)
8. [Testing](#testing)
9. [Deployment](#deployment)
10. [Contributing](#contributing)

---

## Architecture Overview

SecureMedia is a Flask-based web application that provides end-to-end media protection:

```
┌──────────────────────────────────────────────────────────┐
│                     Nginx (HTTPS)                        │
│              TLS termination · rate limiting              │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│                   Gunicorn (WSGI)                         │
│              4 workers · 2 threads each                   │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│                    Flask App                              │
│                                                          │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐               │
│  │ Auth BP │  │ Media BP │  │ Admin BP │               │
│  │/auth/*  │  │ / *      │  │/admin/*  │               │
│  └────┬────┘  └────┬─────┘  └────┬─────┘               │
│       │            │             │                       │
│  ┌────▼────────────▼─────────────▼─────┐                │
│  │         Core Services               │                │
│  │  ┌────────────┐  ┌───────────────┐  │                │
│  │  │ Encryption │  │  Watermarking │  │                │
│  │  │ AES-256-GCM│  │ Spread-Spec.  │  │                │
│  │  │ + Fernet   │  │ + DWT Video   │  │                │
│  │  └────────────┘  └───────────────┘  │                │
│  │  ┌────────────┐  ┌───────────────┐  │                │
│  │  │    KMS     │  │ Policy Engine │  │                │
│  │  │ Shamir SSS │  │ RBAC + ABAC   │  │                │
│  │  └────────────┘  └───────────────┘  │                │
│  └─────────────────────────────────────┘                │
│                                                          │
│  ┌──────────────┐  ┌───────────┐  ┌──────────────┐     │
│  │  SQLAlchemy  │  │  Storage  │  │  Audit Log   │     │
│  │ SQLite/PgSQL │  │ Local/S3  │  │  DB Table    │     │
│  └──────────────┘  └───────────┘  └──────────────┘     │
└──────────────────────────────────────────────────────────┘
```

### Upload Flow
1. User authenticates via Flask-Login session
2. File uploaded via multipart form POST
3. Watermark payload generated (user ID + timestamp)
4. Watermark embedded (spread-spectrum audio / DWT video)
5. Watermarked file encrypted with AES-256-GCM
6. AES key wrapped with Fernet and stored in DB
7. Key optionally split via Shamir's Secret Sharing
8. Encrypted `.enc` file stored on disk
9. Audit log entry created

### Download Flow
1. Policy Engine checks user access (RBAC + ABAC)
2. Key retrieved from KMS (reconstructed if split)
3. File decrypted with AES-256-GCM
4. Watermark extracted and verified
5. Plaintext file streamed to user
6. Audit log entry created

---

## Project Structure

```
videoaudioenc/
├── app/
│   ├── __init__.py          # App factory, extensions, error handlers
│   ├── models.py            # User, MediaFile, AuditLog models
│   ├── encryption.py        # AES-256-GCM + Fernet key wrapping
│   ├── kms.py               # Key Management Service + Shamir SSS
│   ├── policy.py            # RBAC/ABAC policy engine (6 policy types + sharing)
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── routes.py        # Register, login, logout
│   │   └── forms.py         # WTForms for auth
│   ├── media/
│   │   ├── __init__.py
│   │   └── routes.py        # Dashboard, upload, download, share, verify, REST API
│   ├── admin/
│   │   ├── __init__.py
│   │   └── routes.py        # Key/user/policy/audit management
│   ├── watermark/
│   │   ├── __init__.py      # Unified embed/extract API
│   │   ├── audio.py         # Spread-spectrum audio watermarking
│   │   └── video.py         # DWT-based video watermarking
│   └── templates/           # Jinja2 templates (Bootstrap 5.3.3 dark theme)
│       ├── base.html        # Layout + step-by-step upload spinner
│       ├── dashboard.html   # Stats + files + shared-with-me section
│       ├── upload.html      # Drag-drop upload form
│       ├── profile.html     # User profile
│       ├── file_detail.html # File info + sharing card + contextual actions
│       ├── verify_encryption.html  # 10-point encryption verification
│       ├── auth/            # Login, register
│       ├── admin/           # Keys, policies, users, audit
│       └── errors/          # 403, 404, 500 pages
├── tests/
│   ├── test_encryption.py          # Phase 2: Basic crypto (8 tests)
│   ├── test_kms_policy.py          # Phase 4: KMS + policy (20 tests)
│   ├── test_watermark.py           # Phase 3: Watermark basics (7 tests)
│   ├── test_routes.py              # Phase 4: Auth/media routes (8 tests)
│   ├── test_phase5.py              # Phase 5: UI/API/admin (27 tests)
│   ├── test_phase6_encryption.py   # Phase 6: Edge cases + tampering (29 tests)
│   ├── test_phase6_watermark.py    # Phase 6: Fidelity + robustness (15 tests)
│   └── test_phase6_integration.py  # Phase 6: E2E + penetration (21 tests)
├── docs/                    # Documentation
├── nginx/                   # Nginx reverse proxy config
│   └── nginx.conf
├── .github/workflows/       # CI/CD pipeline
│   └── ci-cd.yml
├── config.py                # Dev/Test/Prod configurations
├── run.py                   # Development entry point
├── wsgi.py                  # Production entry point (Gunicorn)
├── Dockerfile               # Multi-stage production image
├── docker-compose.yml       # Full stack orchestration
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
└── .gitignore
```

---

## Local Development Setup

### Prerequisites
- Python 3.12+
- FFmpeg (for audio/video processing)
- Git

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/Gopi1603/videoaudio.git
cd videoaudio

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate    # Linux/Mac
venv\Scripts\activate       # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variable (optional — auto-generated if not set)
export FERNET_MASTER_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# 5. Run the development server
python run.py
# → http://127.0.0.1:5000

# 6. (Optional) Seed admin account
flask seed-admin
# → admin@securemedia.local / Admin@1234

# 7. Run tests
python -m pytest tests/ -v --tb=short
```

---

## Docker Development

```bash
# 1. Copy environment file
cp .env.example .env
# Edit .env with your SECRET_KEY and FERNET_MASTER_KEY

# 2. Build and run
docker compose up --build

# 3. Access the app
# → http://localhost:8000 (direct to Gunicorn)
# → https://localhost (via Nginx, requires certs in nginx/certs/)

# 4. Run tests inside container
docker compose exec web python -m pytest tests/ -v

# 5. Seed admin
docker compose exec web flask seed-admin

# 6. Stop
docker compose down
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret-...` | Flask session signing key |
| `FERNET_MASTER_KEY` | Auto-generated | Fernet key for AES key wrapping |
| `DATABASE_URL` | `sqlite:///app.db` | Database connection string |
| `FLASK_ENV` | `development` | Environment (development/production) |
| `MAX_CONTENT_LENGTH` | 500 MB | Maximum upload file size |
| `PORT` | 8000 | Gunicorn listen port |

### Config Classes
- **`DevelopmentConfig`** — `DEBUG=True`, SQLite, auto-generated keys
- **`TestingConfig`** — In-memory SQLite, CSRF disabled
- **`ProductionConfig`** — `DEBUG=False`, secure cookies, HTTPS-only

---

## Database Models

### User
| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `username` | String(80) | Unique, indexed |
| `email` | String(120) | Unique, indexed |
| `password_hash` | String(256) | Werkzeug PBKDF2 |
| `role` | String(20) | `"user"` or `"admin"` |
| `created_at` | DateTime | UTC timestamp |

### MediaFile
| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `owner_id` | FK → users.id | File owner |
| `original_filename` | String(255) | Original name |
| `stored_filename` | String(255) | UUID-based `.enc` name |
| `file_size` | Integer | Original size in bytes |
| `mime_type` | String(100) | MIME type |
| `status` | String(20) | `"encrypted"` / `"deleted"` |
| `encrypted_key` | Text | Fernet-wrapped AES key |
| `watermark_payload` | String(255) | `"uid:3\|ts:1707500000"` |
| `watermark_id` | String(64) | Short hash for display |

### AuditLog
| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `user_id` | FK → users.id | Actor (nullable) |
| `action` | String(50) | `login`, `upload`, `download`, `delete`, etc. |
| `media_id` | FK → media_files.id | Related file (nullable) |
| `result` | String(20) | `"success"` / `"failure"` |
| `detail` | Text | Structured metadata |
| `timestamp` | DateTime | UTC timestamp |

### KeyRecord, KeyShare, Policy, PolicyLog
See `app/kms.py` and `app/policy.py` for full schema definitions.

---

## Module Reference

### `app/encryption.py`
- `generate_file_key()` → 32-byte AES-256 key
- `wrap_key(key)` → Fernet-encrypted string
- `unwrap_key(wrapped)` → raw AES key bytes
- `encrypt_bytes(plaintext, key)` → `nonce(12B) || ciphertext+tag`
- `decrypt_bytes(blob, key)` → plaintext bytes
- `encrypt_file(src, dst)` → `(wrapped_key, metadata)`
- `decrypt_file(src, dst, wrapped_key)` → metadata

### `app/kms.py`
- `split_secret(secret, n, k)` → Shamir shares
- `reconstruct_secret(shares, k)` → original bytes
- `store_key(media_id, key, ...)` → KeyRecord
- `retrieve_key(media_id)` → AES key or None
- `revoke_key(media_id)` → bool
- `generate_file_key()` → 32-byte key

### `app/policy.py`
- `PolicyType` enum: `OWNER_ONLY`, `ADMIN_OVERRIDE`, `SHARED`, `TIME_LIMITED`, `MULTI_PARTY`, `CUSTOM`
- `check_access(user_id, user_role, file_id, owner_id)` → `AccessDecision`
- `share_file(media_id, user_ids, shared_by)` → creates SHARED policies for each user
- `revoke_share(media_id, user_id)` → removes SHARED policy for user
- `create_policy(media_id, policy_type, ...)` → Policy
- `get_file_policies(media_id)` → list

### `app/watermark/`
- `embed_watermark(src, dst, payload)` → metadata dict
- `extract_watermark(src, payload_length)` → dict with `payload`, `confidence`
- Audio: spread-spectrum encoding (44.1 kHz, 16-bit)
- Video: DWT (Discrete Wavelet Transform) per-frame embedding

---

## Testing

```bash
# Run all 136 tests
python -m pytest tests/ -v --tb=short

# Run with coverage
python -m pytest tests/ --cov=app --cov-report=term-missing --cov-report=html

# Run specific test file
python -m pytest tests/test_phase6_encryption.py -v -s

# Run specific test class
python -m pytest tests/test_phase6_integration.py::TestPolicyPenetration -v
```

### Test Coverage by Phase
| Phase | File | Tests | Domain |
|-------|------|-------|--------|
| 2 | `test_encryption.py` | 8 | AES-GCM + Fernet basics |
| 3 | `test_watermark.py` | 7 | Audio/video watermark |
| 4 | `test_kms_policy.py` | 20 | Shamir SSS, KMS, RBAC/ABAC |
| 4 | `test_routes.py` | 8 | Auth, upload, download |
| 5 | `test_phase5.py` | 27 | UI, REST API, admin |
| 6 | `test_phase6_encryption.py` | 29 | Edge cases, tampering |
| 6 | `test_phase6_watermark.py` | 15 | Fidelity, robustness |
| 6 | `test_phase6_integration.py` | 22 | E2E, penetration, sharing, audit |
| **Total** | | **136** | |

---

## Deployment

### Option A: Docker Compose (Recommended)
```bash
cp .env.example .env    # Configure secrets
docker compose up -d    # App + PostgreSQL + Nginx
```

### Option B: Manual Deployment
```bash
pip install -r requirements.txt
export FLASK_ENV=production
export SECRET_KEY="your-secure-key"
export FERNET_MASTER_KEY="your-fernet-key"
export DATABASE_URL="postgresql://user:pass@host/db"
gunicorn --bind 0.0.0.0:8000 --workers 4 wsgi:app
```

### Option C: Cloud (AWS)
1. Push Docker image to ECR
2. Deploy via ECS/Fargate or EC2
3. Use RDS PostgreSQL for database
4. Use S3 with SSE-S3 for media storage
5. Use ALB with ACM certificate for HTTPS
6. Set environment variables via Secrets Manager

### SSL/TLS Certificates
```bash
# Self-signed (development)
mkdir -p nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/privkey.pem \
  -out nginx/certs/fullchain.pem \
  -subj "/CN=localhost"

# Let's Encrypt (production)
certbot certonly --standalone -d yourdomain.com
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/certs/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/certs/
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Write tests for your changes
4. Ensure all 136+ tests pass: `python -m pytest tests/ -v`
5. Commit with descriptive messages
6. Push and open a Pull Request

### Code Style
- Python 3.12+ type hints
- Max line length: 120 characters
- Docstrings for all public functions
- Tests required for new features
