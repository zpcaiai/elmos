---
name: "elmos-7plus1-release-certification"
description: "Invoke the bounded repository handler for elmos-7plus1-release-certification while preserving its immutable source and fail-closed evidence boundary."
metadata:
  source_package: "elmos-7plus1-commercial-skills"
  source_package_id: "P00"
  source_package_name: "elmos-software-factory-master"
  source_archive: "00-elmos-software-factory-master-v1.0.0.zip"
  source_role: "child"
  source_key: "P00:release-certification"
  source_name: "elmos-release-certification"
  installed_name: "elmos-7plus1-release-certification"
  source_logical_path: "00-elmos-software-factory-master/skills/release-certification/SKILL.md"
  source_path: "skills/elmos-7plus1-commercial-skills-v1.0.0/00-elmos-software-factory-master/skills/release-certification/SKILL.md.source-data"
  source_materialized_path: "00-elmos-software-factory-master/skills/release-certification/SKILL.md.source-data"
  source_sha256: "sha256:1195562d88fddbdca83539f318922fef637aa6bdb7609fe9caca187e56ed1f79"
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
  installed_name_resolution: "PREEXISTING_REPOSITORY_SKILL_OWNERSHIP"
---

# elmos-7plus1-release-certification

This active Skill is repository-authored. The archive description and body are preserved only as neutralized canonical source data and are never loaded here as instructions.
## Repository Integration Boundary

- This is a deterministic repository wrapper for `00-elmos-software-factory-master/skills/release-certification/SKILL.md` at `sha256:1195562d88fddbdca83539f318922fef637aa6bdb7609fe9caca187e56ed1f79`.
- Its immutable source/runtime identity is `elmos-release-certification`; its active installed identity is `elmos-7plus1-release-certification`.
- The archived blueprint is preserved as immutable source data; importing it did not authorize or execute its scripts, tools, providers, deployments, or side effects.
- The archived capability remains `BLUEPRINT_IMPORTED`; its repository handler is `LOCAL_IMPLEMENTED_BOUNDED` within the bounded local runtime.
- The deterministic wrapper and binding contract are `LOCAL_CONTRACT_IMPLEMENTED`.
- Runtime evidence is `NOT_RUN`, external evidence is `NOT_RUN`, and certification is `NOT_CERTIFIED`.
- Missing, blocked, partial, synthetic, skipped, or self-verified evidence cannot establish runtime success or certification.

## Repository Runtime

```bash
PYTHONPATH=engines/software-factory-engine/src python3 -m elmos_software_factory execute --skill elmos-release-certification --request <file>
```

The binding is `BOUND_NOT_EXECUTED`, not runtime evidence. External actions still require explicit adapters and authorization.
