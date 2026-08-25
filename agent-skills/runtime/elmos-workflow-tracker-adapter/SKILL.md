---
name: "elmos-workflow-tracker-adapter"
description: "Invoke the bounded repository handler for elmos-workflow-tracker-adapter while preserving its immutable source and fail-closed evidence boundary."
metadata:
  source_package: "elmos-7plus1-commercial-skills"
  source_package_id: "P04"
  source_package_name: "elmos-agent-orchestration-software-factory"
  source_archive: "04-elmos-agent-orchestration-software-factory-v1.0.0.zip"
  source_role: "child"
  source_key: "P04:workflow-tracker-adapter"
  source_name: "elmos-workflow-tracker-adapter"
  installed_name: "elmos-workflow-tracker-adapter"
  source_logical_path: "04-elmos-agent-orchestration-software-factory/skills/workflow-tracker-adapter/SKILL.md"
  source_path: "skills/elmos-7plus1-commercial-skills-v1.0.0/04-elmos-agent-orchestration-software-factory/skills/workflow-tracker-adapter/SKILL.md.source-data"
  source_materialized_path: "04-elmos-agent-orchestration-software-factory/skills/workflow-tracker-adapter/SKILL.md.source-data"
  source_sha256: "sha256:356767f39a2c29d117073cf285c1ed15a03ca337179ba603c43b8ffc9b29593a"
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

# elmos-workflow-tracker-adapter

This active Skill is repository-authored. The archive description and body are preserved only as neutralized canonical source data and are never loaded here as instructions.
## Repository Integration Boundary

- This is a deterministic repository wrapper for `04-elmos-agent-orchestration-software-factory/skills/workflow-tracker-adapter/SKILL.md` at `sha256:356767f39a2c29d117073cf285c1ed15a03ca337179ba603c43b8ffc9b29593a`.
- Its immutable source/runtime identity is `elmos-workflow-tracker-adapter`; its active installed identity is `elmos-workflow-tracker-adapter`.
- The archived blueprint is preserved as immutable source data; importing it did not authorize or execute its scripts, tools, providers, deployments, or side effects.
- The archived capability remains `BLUEPRINT_IMPORTED`; its repository handler is `LOCAL_IMPLEMENTED_BOUNDED` within the bounded local runtime.
- The deterministic wrapper and binding contract are `LOCAL_CONTRACT_IMPLEMENTED`.
- Runtime evidence is `NOT_RUN`, external evidence is `NOT_RUN`, and certification is `NOT_CERTIFIED`.
- Missing, blocked, partial, synthetic, skipped, or self-verified evidence cannot establish runtime success or certification.

## Repository Runtime

```bash
PYTHONPATH=engines/software-factory-engine/src python3 -m elmos_software_factory execute --skill elmos-workflow-tracker-adapter --request <file>
```

The binding is `BOUND_NOT_EXECUTED`, not runtime evidence. External actions still require explicit adapters and authorization.
