---
name: incident-triage-remediation-and-postmortem
description: Repository-owned bounded FDE capability handler for incident-triage-remediation-and-postmortem; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 06-verification-release-operations
  source_id: incident-triage-remediation-and-postmortem
  alias: incident-triage-remediation-and-postmortem
  handler: elmos_fde_delivery.handlers.operations:execute_incident_triage_remediation_and_postmortem
  dependencies:
  - runtime-observation-and-traffic-capture
  - shadow-dual-run-canary-rollback-preparation
  effect_boundary: E3
  routable: false
---

# incident-triage-remediation-and-postmortem

This skill provides the repository-owned bounded implementation for `incident-triage-remediation-and-postmortem` in pack `06-verification-release-operations`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
