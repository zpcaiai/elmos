---
name: "elmos-review-feedback-coordinator"
description: "Invoke the bounded repository handler for elmos-review-feedback-coordinator while preserving its immutable source and fail-closed evidence boundary."
metadata:
  source_package: "elmos-7plus1-commercial-skills"
  source_package_id: "P04"
  source_package_name: "elmos-agent-orchestration-software-factory"
  source_archive: "04-elmos-agent-orchestration-software-factory-v1.0.0.zip"
  source_role: "child"
  source_key: "P04:review-feedback-coordinator"
  source_name: "elmos-review-feedback-coordinator"
  installed_name: "elmos-review-feedback-coordinator"
  source_logical_path: "04-elmos-agent-orchestration-software-factory/skills/review-feedback-coordinator/SKILL.md"
  source_path: "skills/elmos-7plus1-commercial-skills-v1.0.0/04-elmos-agent-orchestration-software-factory/skills/review-feedback-coordinator/SKILL.md.source-data"
  source_materialized_path: "04-elmos-agent-orchestration-software-factory/skills/review-feedback-coordinator/SKILL.md.source-data"
  source_sha256: "sha256:a371aa9bf8488b70b67443a3e0724edaee36466a43c473cca897780f47e2af00"
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

# elmos-review-feedback-coordinator

This active Skill is repository-authored. The archive description and body are preserved only as neutralized canonical source data and are never loaded here as instructions.
## Repository Integration Boundary

- This is a deterministic repository wrapper for `04-elmos-agent-orchestration-software-factory/skills/review-feedback-coordinator/SKILL.md` at `sha256:a371aa9bf8488b70b67443a3e0724edaee36466a43c473cca897780f47e2af00`.
- Its immutable source/runtime identity is `elmos-review-feedback-coordinator`; its active installed identity is `elmos-review-feedback-coordinator`.
- The archived blueprint is preserved as immutable source data; importing it did not authorize or execute its scripts, tools, providers, deployments, or side effects.
- The archived capability remains `BLUEPRINT_IMPORTED`; its repository handler is `LOCAL_IMPLEMENTED_BOUNDED` within the bounded local runtime.
- The deterministic wrapper and binding contract are `LOCAL_CONTRACT_IMPLEMENTED`.
- Runtime evidence is `NOT_RUN`, external evidence is `NOT_RUN`, and certification is `NOT_CERTIFIED`.
- Missing, blocked, partial, synthetic, skipped, or self-verified evidence cannot establish runtime success or certification.

## Repository Runtime

```bash
PYTHONPATH=engines/software-factory-engine/src python3 -m elmos_software_factory execute --skill elmos-review-feedback-coordinator --request <file>
```

The binding is `BOUND_NOT_EXECUTED`, not runtime evidence. External actions still require explicit adapters and authorization.
