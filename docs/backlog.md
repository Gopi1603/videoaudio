# Project Backlog & Timeline

## Timeline (Aligned to Phases)
- **Phase 1 (Discovery & Planning)**: Architecture, tech stack decisions, backlog, risks, initial prototypes (optional).
- **Phase 2 (Prototype Development)**: Flask scaffold, auth, upload/download, AES-GCM+Fernet encryption demo.
- **Phase 3 (Watermarking Integration)**: Audio/video watermark embed/extract, quality checks.
- **Phase 4 (Key Management & Policy Engine)**: KMS, key splitting, admin controls, policy enforcement.
- **Phase 5 (Frontend & API Completion)**: UI templates, API polish, role-based access.
- **Phase 6 (Testing & Validation)**: Unit/integration tests, performance metrics, robustness checks.
- **Phase 7 (Deployment & Documentation)**: Docker, cloud deployment, final docs.

## Backlog (Phase 1 Deliverables)
- [x] Architecture document
- [x] Tech stack decision log
- [x] Project backlog & timeline
- [x] Optional crypto prototype scripts (AES-GCM/Fernet)

## Post-Phase Deliverables (All Phases Complete)
- [x] Phase 2: Flask scaffold, auth, upload/download, AES-GCM+Fernet encryption
- [x] Phase 3: Audio/video watermarking integration (spread-spectrum + DWT)
- [x] Phase 4: KMS (Shamir SSS), policy engine (RBAC+ABAC), admin panel
- [x] Phase 5: Full UI (Bootstrap 5.3 dark theme), REST API, error handling
- [x] Phase 6: 136 tests (encryption, watermark, KMS, policy, E2E, penetration)
- [x] Phase 7: Docker + Nginx + CI/CD, full documentation set
- [x] **Bonus: Policy-based file sharing** (share/revoke with audit trail)
- [x] **Bonus: Encryption verification** (10-point checker page)
- [x] **Bonus: Download encrypted** (raw ciphertext export)
- [x] **Bonus: Step-by-step upload spinner** (pipeline progress UI)
- [x] **Bonus: "Shared with Me" dashboard** (shared files section + stat card)

## Risks & Mitigations (Phase 1)
- **Watermark fidelity**: Validate imperceptibility early with small experiments.
- **Performance bottlenecks**: Plan for async/background processing.
- **Key compromise**: Store encrypted keys, restrict KMS access.
