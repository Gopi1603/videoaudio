# Architecture Document

## Overview
A Flask-based web application that embeds an imperceptible watermark into audio/video, then encrypts media using AES-GCM and wraps keys using Fernet. Media is stored in cloud or local storage. Access is governed by a Policy Engine and a Key Management System (KMS), with audit logging for all critical actions.

## Core Components
- **Interaction Module (UI/API)**: Flask routes for login, upload, download, admin actions.
- **User & Auth Module**: Registration/login, role management (Admin, Standard User), session handling.
- **Media Module**: Upload/download orchestration; watermark embedding and extraction; encryption/decryption.
- **Watermarking Module**: Audio/video watermark embed/extract routines.
- **Encryption Module**: AES-GCM for media encryption; Fernet for key wrapping or metadata encryption; PBKDF2HMAC for key derivation if needed.
- **KMS**: Generates and stores per-file keys; supports optional Shamir’s Secret Sharing; key retrieval and revocation.
- **Policy Engine**: Enforces role-based/attribute-based access policies for decrypt requests.
- **Storage**: Local filesystem for dev, cloud object storage for production.
- **Audit Logging**: Logs upload/download, policy checks, key events, watermark verification.

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
2. Policy Engine verifies access to file.
3. KMS retrieves/reconstructs key (if shares required).
4. AES-GCM decrypts media.
5. Watermark extracted and verified.
6. Decrypted media returned; audit log recorded.

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
