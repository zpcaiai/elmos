---
name: "elmos-proof-of-work-assembler"
description: "Invoke the bounded repository handler for elmos-proof-of-work-assembler while preserving its immutable source and fail-closed evidence boundary."
metadata:
  source_package: "elmos-7plus1-commercial-skills"
  source_package_id: "P04"
  source_package_name: "elmos-agent-orchestration-software-factory"
  source_archive: "04-elmos-agent-orchestration-software-factory-v1.0.0.zip"
  source_role: "child"
  source_key: "P04:proof-of-work-assembler"
  source_name: "elmos-proof-of-work-assembler"
  installed_name: "elmos-proof-of-work-assembler"
  source_logical_path: "04-elmos-agent-orchestration-software-factory/skills/proof-of-work-assembler/SKILL.md"
  source_path: "skills/elmos-7plus1-commercial-skills-v1.0.0/04-elmos-agent-orchestration-software-factory/skills/proof-of-work-assembler/SKILL.md.source-data"
  source_materialized_path: "04-elmos-agent-orchestration-software-factory/skills/proof-of-work-assembler/SKILL.md.source-data"
  source_sha256: "sha256:02a3dc00f7df6ba9f8c7c5e9043d98907a232c85aa5b3ef385674894c2927ae0"
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

# elmos-proof-of-work-assembler

This active Skill is repository-authored. The archive description and body are preserved only as neutralized canonical source data and are never loaded here as instructions.
## Repository Integration Boundary

- This is a deterministic repository wrapper for `04-elmos-agent-orchestration-software-factory/skills/proof-of-work-assembler/SKILL.md` at `sha256:02a3dc00f7df6ba9f8c7c5e9043d98907a232c85aa5b3ef385674894c2927ae0`.
- Its immutable source/runtime identity is `elmos-proof-of-work-assembler`; its active installed identity is `elmos-proof-of-work-assembler`.
- The archived blueprint is preserved as immutable source data; importing it did not authorize or execute its scripts, tools, providers, deployments, or side effects.
- The archived capability remains `BLUEPRINT_IMPORTED`; its repository handler is `LOCAL_IMPLEMENTED_BOUNDED` within the bounded local runtime.
- The deterministic wrapper and binding contract are `LOCAL_CONTRACT_IMPLEMENTED`.
- Runtime evidence is `NOT_RUN`, external evidence is `NOT_RUN`, and certification is `NOT_CERTIFIED`.
- Missing, blocked, partial, synthetic, skipped, or self-verified evidence cannot establish runtime success or certification.

## Repository Runtime

```bash
PYTHONPATH=engines/software-factory-engine/src python3 -m elmos_software_factory execute --skill elmos-proof-of-work-assembler --request <file>
```

The binding is `BOUND_NOT_EXECUTED`, not runtime evidence. External actions still require explicit adapters and authorization.
