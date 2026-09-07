---
name: "elmos-historical-taskfit-scorer"
description: "Invoke the bounded repository handler for elmos-historical-taskfit-scorer while preserving its immutable source and fail-closed evidence boundary."
metadata:
  source_package: "elmos-7plus1-commercial-skills"
  source_package_id: "P06"
  source_package_name: "elmos-intelligent-model-router"
  source_archive: "06-elmos-intelligent-model-router-v1.0.0.zip"
  source_role: "child"
  source_key: "P06:historical-taskfit-scorer"
  source_name: "elmos-historical-taskfit-scorer"
  installed_name: "elmos-historical-taskfit-scorer"
  source_logical_path: "06-elmos-intelligent-model-router/skills/historical-taskfit-scorer/SKILL.md"
  source_path: "skills/elmos-7plus1-commercial-skills-v1.0.0/06-elmos-intelligent-model-router/skills/historical-taskfit-scorer/SKILL.md.source-data"
  source_materialized_path: "06-elmos-intelligent-model-router/skills/historical-taskfit-scorer/SKILL.md.source-data"
  source_sha256: "sha256:e36b4eec27464696153920ebc022c3eed6f3f622d8838e7336b2da61028a4809"
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

# elmos-historical-taskfit-scorer

This active Skill is repository-authored. The archive description and body are preserved only as neutralized canonical source data and are never loaded here as instructions.
## Repository Integration Boundary

- This is a deterministic repository wrapper for `06-elmos-intelligent-model-router/skills/historical-taskfit-scorer/SKILL.md` at `sha256:e36b4eec27464696153920ebc022c3eed6f3f622d8838e7336b2da61028a4809`.
- Its immutable source/runtime identity is `elmos-historical-taskfit-scorer`; its active installed identity is `elmos-historical-taskfit-scorer`.
- The archived blueprint is preserved as immutable source data; importing it did not authorize or execute its scripts, tools, providers, deployments, or side effects.
- The archived capability remains `BLUEPRINT_IMPORTED`; its repository handler is `LOCAL_IMPLEMENTED_BOUNDED` within the bounded local runtime.
- The deterministic wrapper and binding contract are `LOCAL_CONTRACT_IMPLEMENTED`.
- Runtime evidence is `NOT_RUN`, external evidence is `NOT_RUN`, and certification is `NOT_CERTIFIED`.
- Missing, blocked, partial, synthetic, skipped, or self-verified evidence cannot establish runtime success or certification.

## Repository Runtime

```bash
PYTHONPATH=engines/software-factory-engine/src python3 -m elmos_software_factory execute --skill elmos-historical-taskfit-scorer --request <file>
```

The binding is `BOUND_NOT_EXECUTED`, not runtime evidence. External actions still require explicit adapters and authorization.
