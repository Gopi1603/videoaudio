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

## Risks & Mitigations (Phase 1)
- **Watermark fidelity**: Validate imperceptibility early with small experiments.
- **Performance bottlenecks**: Plan for async/background processing.
- **Key compromise**: Store encrypted keys, restrict KMS access.
