# Final Report — SecureMedia

**Project:** Digital Audio & Video Encryption with Watermarking Scheme (Flask Web App)  

---
## Introduction
In recent years, the storage and sharing of digital audio and video
content have increased significantly, especially in educational
institutions. Storing such sensitive multimedia data in third-party
storage systems raises concerns regarding privacy, unauthorized
access, data tampering, and ownership protection.

To address these issues, this project proposes a Digital Audio &
Video Encryption with Watermarking Scheme that combines
cryptographic encryption techniques with forensic watermarking.
The system ensures confidentiality, integrity, and traceability of
audio and video content.


## Executive Summary
SecureMedia is a production-ready Flask application that protects audio and video files using AES‑256‑GCM encryption, Fernet key wrapping, and forensic watermarking. It delivers secure upload, controlled access, and audit‑ready download flows, with a full admin panel for keys, policies, and users. The system enforces RBAC + ABAC policies, logs all critical actions, and supports Docker‑based deployment with CI/CD.

---

## Goals & Outcomes
**Primary goals achieved:**
- End‑to‑end encryption for media files (AES‑256‑GCM)
- Secure key handling via Fernet and optional Shamir’s Secret Sharing
- Audio/video forensic watermarking integrated into upload pipeline
- Role‑based + attribute‑based access control with audit trails
- Production‑ready deployment stack and documentation

---
## Existing System
In existing systems, Discrete Fourier Transform (DFT) and
Signal-to-Error Ratio (SER) based techniques are commonly used
for audio and video watermarking. These methods transform
signals into the frequency domain and embed watermark data
within selected frequency components.

### Limitations
- Vulnerable to signal processing and compression attacks
- Loss of information during transformations
- Limited watermark capacity
- No integrated encryption or access control



## Architecture Overview
**Core modules:**
- **Auth Module:** registration/login, session handling, role checks
- **Media Module:** upload, download, file detail, dashboard, sharing, verify encryption
- **Encryption Module:** AES‑GCM + Fernet wrapping (`app/encryption.py`)
- **Watermarking Module:** audio (spread‑spectrum), video (DWT) (`app/watermark/`)
- **KMS Module:** key storage, Shamir's Secret Sharing (`app/kms.py`)
- **Policy Engine:** RBAC + ABAC rules, file sharing (`app/policy.py`)
- **Admin Module:** users, policies, key management, audit logs

A full UML set is available in [docs/uml-diagrams.md](docs/uml-diagrams.md).

---
## Proposed System
The proposed system enhances multimedia security by integrating
AES-GCM based authenticated encryption with Fernet key
management and forensic watermarking. Unlike existing systems,
this approach ensures both confidentiality and integrity while
preserving audio and video quality.



## Security & Compliance
- **Encryption:** AES‑256‑GCM authenticated encryption per file
- **Key wrapping:** Fernet tokens stored in DB
- **Key splitting:** Shamir’s Secret Sharing for multi‑party access
- **Access control:** RBAC + ABAC policies enforced on downloads
- **Audit logging:** login, upload, download, delete, and policy events
- **CSRF protection:** enabled globally for forms

---

## Implementation Highlights
### 1) Upload Pipeline
1. Validate file type (audio/video only)
2. Embed watermark payload (`uid` + timestamp)
3. Encrypt with AES‑GCM
4. Wrap key with Fernet
5. Persist metadata + audit log
6. Step-by-step spinner UI: Preparing → Watermark → AES-256-GCM → Fernet → KMS → Uploading → Done

### 2) Download Pipeline
1. Verify access via policy engine (owner, admin, or shared user)
2. Decrypt file using Fernet‑unwrapped AES key
3. Optionally extract watermark to verify payload
4. Record audit log

### 3) Policy-Based File Sharing
1. File owner selects users to share with
2. Policy engine creates SHARED policies for each recipient
3. Shared users see file in "Shared with Me" dashboard section
4. Shared users can download (decrypted) or download encrypted
5. Owner can revoke access at any time, instantly removing the policy
6. All share/revoke actions logged to audit trail

### 4) Verify Encryption Page
1. 10-point verification proving a file is truly encrypted
2. Checks: file on disk, magic bytes, Shannon entropy, SHA-256 hash, Fernet key unwrap, AES key length, KMS record, watermark, DB status
3. Visual verdict banner (green PASS / red FAIL) with entropy bar and hex preview

### 5) Download Encrypted File
1. Serves raw AES-GCM ciphertext as `application/octet-stream`
2. File delivered with `.enc` extension for offline storage or forensic analysis
3. Access controlled by policy engine (owner, admin, or shared user)

---

## Testing & Validation
- **Automated tests:** 136 total
- **Latest run:** 136 passed, 0 warnings
- **Coverage areas:**
  - Encryption edge cases and tamper detection
  - Watermark fidelity and robustness
  - KMS + policy enforcement
  - API + UI routes
  - E2E workflow + penetration scenarios

---

## Deployment Readiness
- Docker multi‑stage image
- Docker Compose stack (Flask + PostgreSQL + Nginx)
- Production config hardening (secure cookies, HTTPS preference)
- CI/CD pipeline (lint → test → build → push → deploy)

---

## Known Constraints
- Local dev defaults to SQLite; PostgreSQL requires permissions for schema `public`
- Fernet master key must be valid (32 url‑safe base64 bytes)
- Watermarking depends on audio/video formats supported by ffmpeg/pydub/OpenCV

---

## How to Run
**Local (SQLite):**
1. `pip install -r requirements.txt`
2. `python run.py`
3. Open http://127.0.0.1:5000

**Docker (Production‑like):**
1. `cp .env.example .env`
2. Set `SECRET_KEY` and `FERNET_MASTER_KEY`
3. `docker compose up --build`

---

## Deliverables
- ✅ Source code and full test suite (136 tests)
- ✅ Deployment stack (Docker + Nginx + PostgreSQL)
- ✅ Documentation (API, admin, developer guide)
- ✅ UML diagrams (class, sequence, activity, use case)
- ✅ Final security audit checklist
- ✅ Policy-based file sharing (share/revoke with audit trail)
- ✅ Encryption verification page (10-point checker)
- ✅ Encrypted file download (raw ciphertext export)
- ✅ Step-by-step upload spinner with pipeline progress
- ✅ "Shared with Me" dashboard section

---
## System Requirements

### Hardware Requirements
- Processor: Dual Core 2 Duo
- RAM: 4 GB
- Hard Disk: 250 GB

### Software Requirements
- Operating System: Windows 7 / 8 / 10
- Platform: Anaconda
- Programming Language: Python
- Front End: Spyder 3

## Conclusion
SecureMedia meets all functional, security, and deployment requirements for a secure media protection platform. The system is fully tested, production‑ready, and supported by comprehensive documentation and UML diagrams.
