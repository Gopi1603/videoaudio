# UML Diagrams — SecureMedia


---

## 1) Use Case Diagram

```mermaid
flowchart LR
  user((User))
  admin((Admin))

  uc_login[Login]
  uc_register[Register]
  uc_upload[Upload Media]
  uc_watermark[Embed Watermark]
  uc_encrypt[Encrypt Media]
  uc_download[Download Media]
  uc_decrypt[Decrypt Media]
  uc_verify[Verify Watermark]
  uc_profile[View Profile]
  uc_share[Share File]
  uc_revoke[Revoke Share]
  uc_verify_enc[Verify Encryption]
  uc_download_enc[Download Encrypted]
  uc_audit[View Audit Logs]
  uc_keys[Manage Keys]
  uc_policies[Manage Policies]
  uc_users[Manage Users]

  user --> uc_login
  user --> uc_register
  user --> uc_upload
  user --> uc_download
  user --> uc_profile
  user --> uc_verify
  user --> uc_share
  user --> uc_revoke
  user --> uc_verify_enc
  user --> uc_download_enc

  admin --> uc_audit
  admin --> uc_keys
  admin --> uc_policies
  admin --> uc_users

  uc_upload --> uc_watermark --> uc_encrypt
  uc_download --> uc_decrypt --> uc_verify
  uc_share --> uc_revoke
```

---

## 2) Class Diagram (Core Models + Services)

```mermaid
classDiagram
  class User {
    +int id
    +str username
    +str email
    +str password_hash
    +str role
    +datetime created_at
    +bool is_admin
    +set_password(password)
    +check_password(password)
  }

  class MediaFile {
    +int id
    +int owner_id
    +str original_filename
    +str stored_filename
    +int file_size
    +str mime_type
    +str status
    +datetime created_at
    +str encrypted_key
    +str watermark_payload
    +str watermark_id
  }

  class AuditLog {
    +int id
    +int user_id
    +str action
    +int media_id
    +str result
    +str detail
    +datetime timestamp
  }

  class KeyRecord {
    +int id
    +int media_id
    +str encrypted_key
    +int total_shares
    +int threshold
    +str status
    +datetime created_at
    +datetime revoked_at
  }

  class KeyShare {
    +int id
    +int key_record_id
    +int share_index
    +str encrypted_share
    +int holder_id
    +str status
    +datetime created_at
  }

  class Policy {
    +int id
    +int media_id
    +bool is_global
    +str policy_type
    +int priority
    +str allowed_users
    +datetime expires_at
    +int required_approvals
    +str rule_expression
    +int created_by
    +datetime created_at
    +bool enabled
  }

  class PolicyLog {
    +int id
    +int user_id
    +int media_id
    +str action
    +str decision
    +int policy_id
    +str reason
    +datetime timestamp
  }

  class EncryptionService {
    +generate_file_key()
    +wrap_key(key)
    +unwrap_key(wrapped)
    +encrypt_file(src, dst)
    +decrypt_file(src, dst, wrapped)
  }

  class WatermarkService {
    +embed_watermark(src, dst, payload)
    +extract_watermark(path, payload_len)
  }

  class PolicyEngine {
    +evaluate_policy(context)
    +share_file(media_id, user_ids, shared_by)
    +revoke_share(media_id, user_id)
    +check_access(user_id, role, file_id, owner_id)
  }

  class VerifyEngine {
    +check_file_exists(path)
    +check_magic_bytes(path)
    +calculate_entropy(path)
    +compute_sha256(path)
    +verify_fernet_key(key)
    +verify_aes_key_length(key)
    +check_kms_record(media_id)
    +check_watermark(media)
    +check_db_status(media)
  }

  User "1" --> "*" MediaFile : owns
  User "1" --> "*" AuditLog : produces
  MediaFile "1" --> "1" KeyRecord : has
  KeyRecord "1" --> "*" KeyShare : splits
  MediaFile "1" --> "*" Policy : scoped
  Policy "1" --> "*" PolicyLog : logs

  EncryptionService --> MediaFile
  WatermarkService --> MediaFile
  PolicyEngine --> Policy
```

---

## 3) Sequence Diagram (Upload → Watermark → Encrypt)

```mermaid
sequenceDiagram
  participant U as User
  participant UI as Web UI
  participant M as Media Routes
  participant W as Watermark
  participant E as Encryption
  participant DB as Database
  participant FS as File Store

  U->>UI: Select file + submit
  UI->>M: POST /upload
  M->>W: embed_watermark(file, payload)
  W-->>M: watermarked file
  M->>E: encrypt_file(watermarked)
  E-->>M: wrapped_key + metadata
  M->>FS: store encrypted file
  M->>DB: save MediaFile + AuditLog
  DB-->>M: OK
  M-->>UI: success message
```

---

## 4) Sequence Diagram (Download → Policy → Decrypt → Verify)

```mermaid
sequenceDiagram
  participant U as User
  participant UI as Web UI
  participant M as Media Routes
  participant P as Policy Engine
  participant E as Encryption
  participant W as Watermark
  participant DB as Database
  participant FS as File Store

  U->>UI: Click Download
  UI->>M: GET /download/<id>
  M->>DB: fetch MediaFile
  M->>P: evaluate_policy(user, file)
  P-->>M: ALLOW/DENY
  alt ALLOW
    M->>FS: read encrypted file
    M->>E: decrypt_file(encrypted)
    E-->>M: plaintext
    M->>W: extract_watermark(plaintext)
    W-->>M: payload
    M->>DB: write AuditLog
    M-->>UI: send file
  else DENY
    M-->>UI: 403
  end
```

---

## 5) Sequence Diagram (Share File → Policy → Recipient Access)

```mermaid
sequenceDiagram
  participant O as Owner
  participant UI as Web UI
  participant M as Media Routes
  participant P as Policy Engine
  participant DB as Database
  participant R as Recipient

  O->>UI: Select users to share with
  UI->>M: POST /share/<file_id>
  M->>P: share_file(media_id, user_ids, owner_id)
  P->>DB: Create SHARED policies for each user
  DB-->>P: OK
  P-->>M: success
  M->>DB: Write AuditLog (share event)
  M-->>UI: Flash "File shared successfully"

  R->>UI: View Dashboard
  UI->>M: GET /
  M->>DB: Query SHARED policies for recipient
  DB-->>M: List of shared files
  M-->>UI: Show "Shared with Me" section

  R->>UI: Click Download on shared file
  UI->>M: GET /download/<file_id>
  M->>P: check_access(recipient, file)
  P-->>M: ALLOW (shared policy)
  M-->>UI: Stream decrypted file
```

---

## 6) Sequence Diagram (Verify Encryption)

```mermaid
sequenceDiagram
  participant U as User
  participant UI as Web UI
  participant M as Media Routes
  participant FS as File Store
  participant E as Encryption
  participant K as KMS
  participant DB as Database

  U->>UI: Click "Verify Encryption"
  UI->>M: GET /verify/<file_id>
  M->>FS: Check file exists on disk
  M->>FS: Read first 64 bytes (magic bytes check)
  M->>FS: Calculate Shannon entropy
  M->>FS: Compute SHA-256 hash
  M->>E: Unwrap Fernet key test
  M->>E: Check AES key length (32 bytes)
  M->>K: Check KMS record exists
  M->>DB: Check watermark info
  M->>DB: Check file status
  M-->>UI: Render verification results (10 checks)
```

---

## 7) Sequence Diagram (Download Encrypted File)

```mermaid
sequenceDiagram
  participant U as User
  participant UI as Web UI
  participant M as Media Routes
  participant P as Policy Engine
  participant FS as File Store

  U->>UI: Click "Download Encrypted"
  UI->>M: GET /download-encrypted/<file_id>
  M->>P: check_access(user, file)
  P-->>M: ALLOW/DENY
  alt ALLOW
    M->>FS: Read raw .enc ciphertext
    M-->>UI: Send file as application/octet-stream
  else DENY
    M-->>UI: 403 Forbidden
  end
```

---

## 8) Activity Diagram (End-to-End Upload Flow)

```mermaid
flowchart TD
  A([Start]) --> B[User selects file]
  B --> C{File allowed?}
  C -- No --> D[Reject + flash error]
  D --> Z([End])
  C -- Yes --> E[Generate watermark payload]
  E --> F[Embed watermark]
  F --> G[Encrypt with AES‑GCM]
  G --> H[Wrap key with Fernet]
  H --> I[Save encrypted file]
  I --> J[Persist MediaFile + AuditLog]
  J --> K[Show success]
  K --> Z([End])
```
