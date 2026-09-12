---
name: ai-agent-system-audit
description: Repository-owned bounded FDE capability handler for ai-agent-system-audit; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 04-unified-assessment
  source_id: ai-agent-system-audit
  alias: ai-agent-system-audit
  handler: elmos_fde_delivery.handlers.assessment:execute_ai_agent_system_audit
  dependencies:
  - issue-ontology-and-finding-normalization
  - data-event-permission-lineage
  - test-ci-cd-developer-experience-audit
  effect_boundary: E3
  routable: false
---

# ai-agent-system-audit

This skill provides the repository-owned bounded implementation for `ai-agent-system-audit` in pack `04-unified-assessment`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
