---
name: elmos-fde-correctness-concurrency-consistency-audit
description: Repository-owned bounded FDE capability handler for correctness-concurrency-consistency-audit; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 04-unified-assessment
  source_id: correctness-concurrency-consistency-audit
  alias: elmos-fde-correctness-concurrency-consistency-audit
  handler: elmos_fde_delivery.handlers.assessment:execute_correctness_concurrency_consistency_audit
  dependencies:
  - issue-ontology-and-finding-normalization
  - data-event-permission-lineage
  effect_boundary: E3
  routable: false
---

# elmos-fde-correctness-concurrency-consistency-audit

This skill provides the repository-owned bounded implementation for `correctness-concurrency-consistency-audit` in pack `04-unified-assessment`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
