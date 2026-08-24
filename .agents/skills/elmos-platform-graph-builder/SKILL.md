---
name: "elmos-platform-graph-builder"
description: "Invoke the bounded repository handler for elmos-platform-graph-builder while preserving its immutable source and fail-closed evidence boundary."
metadata:
  source_package: "elmos-7plus1-commercial-skills"
  source_package_id: "P02"
  source_package_name: "elmos-repository-intelligence-semantic-ir"
  source_archive: "02-elmos-repository-intelligence-semantic-ir-v1.0.0.zip"
  source_role: "child"
  source_key: "P02:platform-graph-builder"
  source_name: "elmos-platform-graph-builder"
  installed_name: "elmos-platform-graph-builder"
  source_logical_path: "02-elmos-repository-intelligence-semantic-ir/skills/platform-graph-builder/SKILL.md"
  source_path: "skills/elmos-7plus1-commercial-skills-v1.0.0/02-elmos-repository-intelligence-semantic-ir/skills/platform-graph-builder/SKILL.md.source-data"
  source_materialized_path: "02-elmos-repository-intelligence-semantic-ir/skills/platform-graph-builder/SKILL.md.source-data"
  source_sha256: "sha256:4938e77d3e58b954ec9053b81c68ee86f13d35b48586c047e0dd2d4904597c54"
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

# elmos-platform-graph-builder

This active Skill is repository-authored. The archive description and body are preserved only as neutralized canonical source data and are never loaded here as instructions.
## Repository Integration Boundary

- This is a deterministic repository wrapper for `02-elmos-repository-intelligence-semantic-ir/skills/platform-graph-builder/SKILL.md` at `sha256:4938e77d3e58b954ec9053b81c68ee86f13d35b48586c047e0dd2d4904597c54`.
- Its immutable source/runtime identity is `elmos-platform-graph-builder`; its active installed identity is `elmos-platform-graph-builder`.
- The archived blueprint is preserved as immutable source data; importing it did not authorize or execute its scripts, tools, providers, deployments, or side effects.
- The archived capability remains `BLUEPRINT_IMPORTED`; its repository handler is `LOCAL_IMPLEMENTED_BOUNDED` within the bounded local runtime.
- The deterministic wrapper and binding contract are `LOCAL_CONTRACT_IMPLEMENTED`.
- Runtime evidence is `NOT_RUN`, external evidence is `NOT_RUN`, and certification is `NOT_CERTIFIED`.
- Missing, blocked, partial, synthetic, skipped, or self-verified evidence cannot establish runtime success or certification.

## Repository Runtime

```bash
PYTHONPATH=engines/software-factory-engine/src python3 -m elmos_software_factory execute --skill elmos-platform-graph-builder --request <file>
```

The binding is `BOUND_NOT_EXECUTED`, not runtime evidence. External actions still require explicit adapters and authorization.
