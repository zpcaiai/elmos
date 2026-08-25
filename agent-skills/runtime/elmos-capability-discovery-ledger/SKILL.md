---
name: "elmos-capability-discovery-ledger"
description: "Invoke the bounded repository handler for elmos-capability-discovery-ledger while preserving its immutable source and fail-closed evidence boundary."
metadata:
  source_package: "elmos-7plus1-commercial-skills"
  source_package_id: "P02"
  source_package_name: "elmos-repository-intelligence-semantic-ir"
  source_archive: "02-elmos-repository-intelligence-semantic-ir-v1.0.0.zip"
  source_role: "child"
  source_key: "P02:capability-discovery-ledger"
  source_name: "elmos-capability-discovery-ledger"
  installed_name: "elmos-capability-discovery-ledger"
  source_logical_path: "02-elmos-repository-intelligence-semantic-ir/skills/capability-discovery-ledger/SKILL.md"
  source_path: "skills/elmos-7plus1-commercial-skills-v1.0.0/02-elmos-repository-intelligence-semantic-ir/skills/capability-discovery-ledger/SKILL.md.source-data"
  source_materialized_path: "02-elmos-repository-intelligence-semantic-ir/skills/capability-discovery-ledger/SKILL.md.source-data"
  source_sha256: "sha256:525fb2a44bdeab006a09462b1b7aed0e80df83a779fe74f45e8866efd3c9ccfc"
  source_version: "1.0.0"
  normalized_namespace: "elmos-7plus1-commercial-v1"
  integration_state: "LOCAL_CONTRACT_IMPLEMENTED"
  implementation_state: "BLUEPRINT_IMPORTED"
  source_implementation_state: "BLUEPRINT_IMPORTED"
  repository_handler_state: "LOCAL_IMPLEMENTED_BOUNDED"
  runtime_module: "elmos_software_factory"
  runtime_registry: "engines/software-factory-engine/src/elmos_software_factory/skill_registry.json"
  runtime_binding_state: "BOUND_NOT_EXECUTED"
  runtime_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
  installed_name_resolution: "SOURCE_NAME_PRESERVED"
---

# elmos-capability-discovery-ledger

This active Skill is repository-authored. The archive description and body are preserved only as neutralized canonical source data and are never loaded here as instructions.
## Repository Integration Boundary

- This is a deterministic repository wrapper for `02-elmos-repository-intelligence-semantic-ir/skills/capability-discovery-ledger/SKILL.md` at `sha256:525fb2a44bdeab006a09462b1b7aed0e80df83a779fe74f45e8866efd3c9ccfc`.
- Its immutable source/runtime identity is `elmos-capability-discovery-ledger`; its active installed identity is `elmos-capability-discovery-ledger`.
- The archived blueprint is preserved as immutable source data; importing it did not authorize or execute its scripts, tools, providers, deployments, or side effects.
- The archived capability remains `BLUEPRINT_IMPORTED`; its repository handler is `LOCAL_IMPLEMENTED_BOUNDED` within the bounded local runtime.
- The deterministic wrapper and binding contract are `LOCAL_CONTRACT_IMPLEMENTED`.
- Runtime evidence is `NOT_RUN`, external evidence is `NOT_RUN`, and certification is `NOT_CERTIFIED`.
- Missing, blocked, partial, synthetic, skipped, or self-verified evidence cannot establish runtime success or certification.

## Repository Runtime

```bash
PYTHONPATH=engines/software-factory-engine/src python3 -m elmos_software_factory execute --skill elmos-capability-discovery-ledger --request <file>
```

The binding is `BOUND_NOT_EXECUTED`, not runtime evidence. External actions still require explicit adapters and authorization.
