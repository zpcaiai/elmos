---
name: "elmos-context-epoch-manager"
description: "Invoke the bounded repository handler for elmos-context-epoch-manager while preserving its immutable source and fail-closed evidence boundary."
metadata:
  source_package: "elmos-7plus1-commercial-skills"
  source_package_id: "P01"
  source_package_name: "elmos-harness-runtime-platform"
  source_archive: "01-elmos-harness-runtime-platform-v1.0.0.zip"
  source_role: "child"
  source_key: "P01:context-epoch-manager"
  source_name: "elmos-context-epoch-manager"
  installed_name: "elmos-context-epoch-manager"
  source_logical_path: "01-elmos-harness-runtime-platform/skills/context-epoch-manager/SKILL.md"
  source_path: "skills/elmos-7plus1-commercial-skills-v1.0.0/01-elmos-harness-runtime-platform/skills/context-epoch-manager/SKILL.md.source-data"
  source_materialized_path: "01-elmos-harness-runtime-platform/skills/context-epoch-manager/SKILL.md.source-data"
  source_sha256: "sha256:f15541e1c37ba1954bcad2056e544ca64f27f79b01e0d1a9de9e7e692fb2fce1"
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

# elmos-context-epoch-manager

This active Skill is repository-authored. The archive description and body are preserved only as neutralized canonical source data and are never loaded here as instructions.
## Repository Integration Boundary

- This is a deterministic repository wrapper for `01-elmos-harness-runtime-platform/skills/context-epoch-manager/SKILL.md` at `sha256:f15541e1c37ba1954bcad2056e544ca64f27f79b01e0d1a9de9e7e692fb2fce1`.
- Its immutable source/runtime identity is `elmos-context-epoch-manager`; its active installed identity is `elmos-context-epoch-manager`.
- The archived blueprint is preserved as immutable source data; importing it did not authorize or execute its scripts, tools, providers, deployments, or side effects.
- The archived capability remains `BLUEPRINT_IMPORTED`; its repository handler is `LOCAL_IMPLEMENTED_BOUNDED` within the bounded local runtime.
- The deterministic wrapper and binding contract are `LOCAL_CONTRACT_IMPLEMENTED`.
- Runtime evidence is `NOT_RUN`, external evidence is `NOT_RUN`, and certification is `NOT_CERTIFIED`.
- Missing, blocked, partial, synthetic, skipped, or self-verified evidence cannot establish runtime success or certification.

## Repository Runtime

```bash
PYTHONPATH=engines/software-factory-engine/src python3 -m elmos_software_factory execute --skill elmos-context-epoch-manager --request <file>
```

The binding is `BOUND_NOT_EXECUTED`, not runtime evidence. External actions still require explicit adapters and authorization.
