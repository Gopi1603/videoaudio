# Architecture Document

## Overview
A Flask-based web application that embeds an imperceptible watermark into audio/video, then encrypts media using AES-GCM and wraps keys using Fernet. Media is stored in cloud or local storage. Access is governed by a Policy Engine and a Key Management System (KMS), with audit logging for all critical actions.

## Core Components
- **Interaction Module (UI/API)**: Flask routes for login, upload, download, share, verify, admin actions.
- **User & Auth Module**: Registration/login, role management (Admin, Standard User), session handling.
- **Media Module**: Upload/download orchestration; watermark embedding and extraction; encryption/decryption; file sharing (share/revoke); encryption verification.
- **Watermarking Module**: Audio/video watermark embed/extract routines.
- **Encryption Module**: AES-GCM for media encryption; Fernet for key wrapping or metadata encryption; PBKDF2HMAC for key derivation if needed.
- **KMS**: Generates and stores per-file keys; supports optional Shamir's Secret Sharing; key retrieval and revocation.
- **Policy Engine**: Enforces role-based/attribute-based access policies for decrypt requests; manages file sharing (share/revoke) with SHARED policies.
- **Verify Engine**: 10-point encryption verification (file existence, magic bytes, entropy, SHA-256, Fernet key, AES key, KMS, watermark, DB status).
- **Storage**: Local filesystem for dev, cloud object storage for production.
- **Audit Logging**: Logs upload/download, policy checks, key events, watermark verification, share/revoke events.

## Primary Flows
### Upload Flow
1. User authenticates.
2. Media file uploaded via UI/API.
3. Watermark payload created (user ID/session/timestamp).
4. Watermark embedded into media.
5. AES-GCM encrypts watermarked media.
6. KMS stores key (optionally split into shares).
7. Encrypted file stored; audit log recorded.

### Download/Decrypt Flow
1. User authenticates.
2. Policy Engine verifies access to file (owner, admin, or shared user).
3. KMS retrieves/reconstructs key (if shares required).
4. AES-GCM decrypts media.
5. Watermark extracted and verified.
6. Decrypted media returned; audit log recorded.

### File Sharing Flow
1. File owner selects users to share with from the file detail page.
2. POST `/share/<file_id>` creates SHARED policies via the Policy Engine.
3. Each recipient now sees the file in their "Shared with Me" dashboard section.
4. Shared users can view file details, download (decrypted), or download encrypted.
5. Owner can revoke access at any time via POST `/revoke/<file_id>/<user_id>`.
6. All share/revoke actions are logged to the audit trail.

### Verify Encryption Flow
1. User navigates to `/verify/<file_id>`.
2. System runs 10 checks: file on disk, magic bytes, Shannon entropy, SHA-256 hash, Fernet key unwrap, AES key length (32 bytes), KMS record, watermark info, DB status.
3. Results displayed with visual verdict banner (PASS/FAIL), entropy bar, and hex preview.

### Download Encrypted Flow
1. User requests `/download-encrypted/<file_id>`.
2. Policy Engine checks access (owner, admin, or shared user).
3. Raw `.enc` ciphertext served as `application/octet-stream`.
4. No decryption performed — file is delivered as-is for offline storage or forensic analysis.

## Data Model (Draft)
- **User**: id, email, password_hash, role, created_at
- **MediaFile**: id, owner_id, filename, storage_path, watermark_id, created_at, status
- **KeyRecord**: id, media_id, encrypted_key, shares, status, created_at
- **Policy**: id, rule_definition, created_at
- **AuditLog**: id, user_id, action, media_id, result, timestamp, metadata

## Security Considerations
- Enforce HTTPS and secure cookies.
- Store passwords hashed (bcrypt/argon2).
- Encrypt keys at rest (Fernet) and restrict KMS access.
- Validate file types/sizes; scan for malware if required.
- Log and alert on failed policy checks and watermark mismatch.

## Deployment Notes (Draft)
- Use environment variables for secrets.
- Plan for object storage encryption at rest.
- Use background workers for heavy watermarking/encryption if needed.
