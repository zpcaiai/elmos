---
name: shadow-dual-run-canary-rollback-preparation
description: Repository-owned bounded FDE capability handler for shadow-dual-run-canary-rollback-preparation; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 06-verification-release-operations
  source_id: shadow-dual-run-canary-rollback-preparation
  alias: shadow-dual-run-canary-rollback-preparation
  handler: elmos_fde_delivery.handlers.operations:execute_shadow_dual_run_canary_rollback_preparation
  dependencies:
  - e0-e3-readiness-and-evidence-bundle
  - changeset-commit-and-provenance-governance
  effect_boundary: E3
  routable: false
---

# shadow-dual-run-canary-rollback-preparation

This skill provides the repository-owned bounded implementation for `shadow-dual-run-canary-rollback-preparation` in pack `06-verification-release-operations`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
