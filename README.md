# 🔐 SecureMedia — Digital Audio & Video Encryption with Watermarking

[![CI/CD](https://github.com/Gopi1603/videoaudio/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Gopi1603/videoaudio/actions)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-136%20passed-brightgreen.svg)](#testing)

A production-ready Flask web application for **encrypting**, **forensic watermarking**, and **policy-controlled access management** of audio and video files. Built for educational content protection with FERPA-compliant audit logging.

---

## ✨ Features

| Feature | Technology | Description |
|---------|-----------|-------------|
| 🔒 **Encryption** | AES-256-GCM + Fernet | Military-grade authenticated encryption with key wrapping |
| 🏷️ **Watermarking** | Spread-spectrum + DWT | Imperceptible forensic watermarks for audio & video |
| 🔑 **Key Management** | Shamir's Secret Sharing | Split keys into shares, threshold reconstruction |
| 🛡️ **Access Control** | RBAC + ABAC | 6 policy types: owner-only, shared, time-limited, multi-party |
| 🤝 **File Sharing** | Policy-based sharing | Share files with specific users, revoke access anytime |
| ✅ **Verify Encryption** | 10-point checker | Prove files are encrypted: entropy, magic bytes, SHA-256, KMS |
| 📥 **Download Encrypted** | Raw ciphertext export | Download the raw `.enc` file for offline storage or transfer |
| 📋 **Audit Trail** | Full event logging | Every action logged for FERPA compliance |
| 🎨 **Modern UI** | Bootstrap 5.3 dark theme | Responsive dashboard, drag-drop upload, step-by-step spinner |
| 🐳 **Containerized** | Docker + Nginx + PostgreSQL | Production-ready deployment stack |
| 🚀 **CI/CD** | GitHub Actions | Automated lint → test → build → deploy pipeline |

---

## 🚀 Quick Start

### Option 1: Local Development
```bash
git clone https://github.com/Gopi1603/videoaudio.git
cd videoaudio
pip install -r requirements.txt
python run.py                    # → http://127.0.0.1:5000
flask seed-admin                 # Create admin account
```

### Option 2: Docker
```bash
cp .env.example .env             # Configure secrets
docker compose up --build        # → http://localhost:8000
docker compose exec web flask seed-admin
```

### Default Admin Credentials
```
Email:    admin
Password: admin
```
⚠️ **Change these immediately in production!**

---

## 🐘 PostgreSQL Setup (pgAdmin)

**Note:** For local development, SQLite is already configured and works out of the box. Only follow these steps if you want to use PostgreSQL locally or test a production-like stack.

### 1) Create the database
- Open pgAdmin → right-click **Databases** → **Create → Database**
- **Name:** `securemedia`
- **Owner:** `postgres` (or a new user you create)
- Click **Save**

### 2) Create a dedicated user (optional but recommended)
- Expand **Login/Group Roles** → right-click → **Create → Login/Group Role**
- **General** tab → Name: `securemedia_user`
- **Definition** tab → Password: `securemedia_pass`
- **Privileges** tab → Toggle **Can login** to Yes
- Click **Save**

### 3) Grant privileges
- Open **Query Tool** (select the `securemedia` DB → Tools → Query Tool) and run:

```sql
GRANT ALL PRIVILEGES ON DATABASE securemedia TO securemedia_user;
GRANT USAGE, CREATE ON SCHEMA public TO securemedia_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL ON TABLES TO securemedia_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL ON SEQUENCES TO securemedia_user;
```

### 4) Update `.env` (or `config.py`)
Set this before running the app:

```
DATABASE_URL=postgresql://securemedia_user:securemedia_pass@localhost:5432/securemedia
```

### 5) Generate `FERNET_MASTER_KEY`
Run:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output into `FERNET_MASTER_KEY` in `.env`.

### 6) Run the app
The app auto-creates all tables on first run via `db.create_all()`.

#### Auto-created tables
| Table | Purpose |
|------|---------|
| `user` | Users with roles (admin/user) |
| `media_file` | Uploaded encrypted files |
| `encryption_key` | AES keys (Fernet-wrapped) |
| `key_share` | Shamir secret shares |
| `policy` | RBAC/ABAC access policies |
| `audit_log` | Activity logs |

---

## 📸 Screenshots

### Dashboard
- Dark theme with stats cards (total files, storage, watermarked, encrypted, shared with me)
- File table with download, detail, and delete actions
- **Shared with Me** section showing files shared by other users
- Responsive Bootstrap 5.3.3 layout

### Upload
- Drag-and-drop upload zone
- Supports: MP3, WAV, OGG, FLAC, AAC, MP4, AVI, MKV, MOV, WEBM
- Step-by-step upload spinner (Preparing → Watermark → AES-256-GCM → Fernet → KMS → Uploading → Done)

### File Detail
- Full file metadata, encryption info, watermark info, audit log
- **Sharing card**: share with users, view current shares, revoke access
- Contextual actions: owner sees all buttons, shared users see download only
- Info banner for shared files: "This file was shared with you by [owner]"

### Verify Encryption
- 10-point verification page proving a file is truly encrypted
- Checks: file on disk, magic bytes, Shannon entropy, SHA-256 hash, Fernet key, AES key length, KMS record, watermark, DB status
- Visual verdict banner (green PASS / red FAIL), entropy bar, hex preview

### Admin Panel
- User management (promote/demote admin)
- Key management (view, revoke, rotate)
- Policy management (6 policy types)
- Audit log viewer

---

## 🏗️ Architecture

```
Client → Nginx (HTTPS/TLS) → Gunicorn (WSGI) → Flask App
                                                    │
                    ┌───────────────────────────────┤
                    │              │                 │
              Auth Blueprint  Media Blueprint  Admin Blueprint
                    │              │                 │
                    └──────┬───────┘                 │
                           │                         │
              ┌────────────┼─────────────┐          │
              │            │             │          │
         Encryption   Watermarking    KMS     Policy Engine
         AES-256-GCM  Spread-Spec   Shamir    RBAC+ABAC
         + Fernet     + DWT Video    SSS      6 policies
              │            │             │      + Sharing
              └────────────┼─────────────┘          │
                           │                         │
              ┌────────────┼──────────────┐          │
              │            │              │          │
         SQLite/PgSQL  File Storage  Audit Logs  Verify Engine
```

### Key User Flows
- **Upload**: Select file → Watermark → Encrypt AES-256-GCM → Wrap key → Store → Audit
- **Download (Decrypt)**: Policy check → Unwrap key → Decrypt → Verify watermark → Stream
- **Download Encrypted**: Policy check → Serve raw `.enc` ciphertext as-is
- **Verify Encryption**: 10-point check (file, entropy, hash, key, KMS, watermark, DB)
- **Share**: Owner selects users → Policy engine creates SHARED policies → Recipients see file
- **Revoke**: Owner removes user → Policy deleted → Access removed instantly

---

## 🔐 Security

### Encryption Pipeline
1. **AES-256-GCM**: Authenticated encryption (confidentiality + integrity)
2. **Fernet Key Wrapping**: AES keys encrypted before database storage
3. **12-byte Random Nonce**: Unique per encryption, prevents replay attacks
4. **Tamper Detection**: 7 attack vectors tested — all detected

### Watermarking
- **Audio**: Spread-spectrum encoding, SNR 15–18 dB (imperceptible)
- **Video**: DWT (Discrete Wavelet Transform), PSNR 26+ dB
- **Payload**: `uid:<user_id>|ts:<timestamp>` — forensic traceability

### Access Control
- **RBAC**: Admin and user roles with decorator-based enforcement
- **ABAC**: Owner-only, time-limited, shared, multi-party policies
- **Policy Engine**: Evaluated on every download request

---

## 🧪 Testing

**136 tests** covering all modules — run in ~36 seconds:

```bash
python -m pytest tests/ -v --tb=short
```

| Test Suite | Tests | Coverage |
|-----------|-------|--------|
| Encryption (basic + edge cases + tampering) | 37 | AES-GCM, Fernet, 7 tamper vectors |
| Watermarking (fidelity + robustness + batch) | 22 | SNR, PSNR, noise, resample |
| KMS & Policy (Shamir + RBAC + ABAC) | 20 | Key lifecycle, 6 policy types |
| Routes & Auth | 8 | Register, login, upload, download |
| UI, REST API, Admin | 27 | Profile, file detail, error pages |
| E2E Integration & Penetration | 22 | Lifecycle, 8 attack scenarios, sharing, audit |

### Performance Benchmarks
| Metric | Value |
|--------|-------|
| Encryption speed (10 MB) | 185 MB/s |
| Decryption speed (10 MB) | 288 MB/s |
| Dashboard response | < 2 ms |
| API response | < 2 ms |
| Audio watermark (0.8 MB) | 53 ms |
| Video watermark (90 frames) | 223 ms |

---

## 📁 Project Structure

```
├── app/
│   ├── __init__.py          # App factory + extensions + admin auto-create
│   ├── models.py            # User, MediaFile, AuditLog
│   ├── encryption.py        # AES-256-GCM + Fernet
│   ├── kms.py               # Key Management + Shamir SSS
│   ├── policy.py            # RBAC/ABAC policy engine + sharing
│   ├── auth/                # Authentication blueprint
│   ├── media/               # Media: dashboard, upload, download, share, verify
│   ├── admin/               # Admin management blueprint
│   ├── watermark/           # Audio + video watermarking
│   └── templates/
│       ├── base.html        # Layout + step-by-step upload spinner
│       ├── dashboard.html   # Stats + files + shared-with-me section
│       ├── upload.html      # Drag-drop upload form
│       ├── file_detail.html # File info + sharing card + actions
│       ├── verify_encryption.html  # 10-point encryption verifier
│       ├── profile.html     # User profile page
│       ├── auth/            # Login, register templates
│       ├── admin/           # Keys, policies, users, audit templates
│       └── errors/          # 403, 404, 500 error pages
├── tests/                   # 136 pytest tests
├── docs/                    # Full documentation set
├── nginx/                   # Reverse proxy config
├── .github/workflows/       # CI/CD pipeline
├── Dockerfile               # Multi-stage production image
├── docker-compose.yml       # Full stack orchestration
├── config.py                # Dev/Test/Prod configs
├── run.py                   # Development entry point
├── wsgi.py                  # Production entry point
└── requirements.txt         # Python dependencies
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Developer Guide](docs/developer-guide.md) | Architecture, setup, module reference, deployment |
| [User Guide](docs/user-guide.md) | End-user workflows with step-by-step instructions |
| [Admin & Policy Manual](docs/admin-policy-manual.md) | Admin panel, KMS, policy engine, audit logs |
| [API Reference](docs/api-reference.md) | All endpoints with request/response examples |
| [Architecture](docs/architecture.md) | System design, data flow, component diagram |
| [Security Audit](docs/security-audit-final.md) | 66-point security checklist (all passing) |
| [Phase 6 Validation](docs/phase6-validation-report.md) | Test results, metrics, issue log |
| [Tech Stack](docs/tech-stack.md) | Technology choices and rationale |

---

## 🛠️ Deployment

### Docker Compose (Recommended)
```bash
cp .env.example .env          # Set SECRET_KEY, FERNET_MASTER_KEY, DB credentials
docker compose up -d           # Starts Flask + PostgreSQL + Nginx
```

### Cloud (AWS)
- **Compute**: ECS/Fargate with Docker image
- **Database**: RDS PostgreSQL
- **Storage**: S3 with SSE-S3 encryption at rest
- **HTTPS**: ALB + ACM certificate
- **Secrets**: AWS Secrets Manager for keys

### CI/CD Pipeline
Automated via GitHub Actions:
1. **Lint** → flake8 code quality
2. **Test** → 136 tests with coverage report
3. **Build** → Docker image
4. **Push** → Docker Hub (on version tags)
5. **Deploy** → SSH to production server (on version tags)

---

## 📜 License

This project is developed for educational purposes as part of a Digital Audio & Video Encryption research project.

---

## 🙏 Acknowledgments

- [Cryptography library](https://cryptography.io/) — AES-GCM and Fernet implementation
- [Flask](https://flask.palletsprojects.com/) — Web framework
- [Bootstrap 5](https://getbootstrap.com/) — UI framework
- Research references on watermarking imperceptibility and encryption best practices (see [phases.md](rules/phases.md) for full citations)
