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

  admin --> uc_audit
  admin --> uc_keys
  admin --> uc_policies
  admin --> uc_users

  uc_upload --> uc_watermark --> uc_encrypt
  uc_download --> uc_decrypt --> uc_verify
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

## 5) Activity Diagram (End-to-End Upload Flow)

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
