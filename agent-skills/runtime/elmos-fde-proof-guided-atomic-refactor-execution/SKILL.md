---
name: elmos-fde-proof-guided-atomic-refactor-execution
description: Repository-owned bounded FDE capability handler for proof-guided-atomic-refactor-execution; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 05-planning-transformation
  source_id: proof-guided-atomic-refactor-execution
  alias: elmos-fde-proof-guided-atomic-refactor-execution
  handler: elmos_fde_delivery.handlers.transformation:execute_proof_guided_atomic_refactor_execution
  dependencies:
  - changeset-commit-and-provenance-governance
  effect_boundary: E3
  routable: false
---

# elmos-fde-proof-guided-atomic-refactor-execution

This skill provides the repository-owned bounded implementation for `proof-guided-atomic-refactor-execution` in pack `05-planning-transformation`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
