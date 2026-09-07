---
name: "elmos-7plus1-commercial-software-factory"
description: "Route the eight Elmos commercial software-factory packages through their exact dependency and evidence boundaries."
metadata:
  source_package: "elmos-7plus1-commercial-skills"
  source_version: "1.0.0"
  normalized_namespace: "elmos-7plus1-commercial-v1"
  ownership: "repository-owned"
  archive_member: "false"
  source_skill_count: "101"
  installed_skill_count: "102"
  implementation_state: "LOCAL_IMPLEMENTED_BOUNDED"
  source_implementation_state: "NOT_APPLICABLE_REPOSITORY_OWNED"
  repository_handler_state: "LOCAL_IMPLEMENTED_BOUNDED"
  runtime_module: "elmos_software_factory"
  runtime_registry: "engines/software-factory-engine/src/elmos_software_factory/skill_registry.json"
  runtime_binding_state: "BOUND_NOT_EXECUTED"
  runtime_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

# Elmos 7+1 Commercial Software Factory

This repository-owned orchestrator routes the immutable P00-P07 blueprints. It is not present in, or attributed to, any source ZIP.

## Package routing

- `P00` -> `$elmos-software-factory-master`; dependencies: none
- `P01` -> `$elmos-harness-runtime-platform`; dependencies: `P00`
- `P02` -> `$elmos-repository-intelligence-semantic-ir`; dependencies: `P00`, `P01`
- `P03` -> `$elmos-project-generation-transformation-engine`; dependencies: `P00`, `P01`, `P02`, `P05`
- `P04` -> `$elmos-agent-orchestration-software-factory`; dependencies: `P00`, `P01`, `P02`, `P03`, `P05`, `P06`
- `P05` -> `$elmos-conversion-reliability-verification-harness`; dependencies: `P00`, `P01`, `P02`
- `P06` -> `$elmos-intelligent-model-router`; dependencies: `P00`, `P01`, `P05`
- `P07` -> `$elmos-transformation-learning-evolution`; dependencies: `P00`, `P02`, `P03`, `P05`, `P06`

## Workflow

1. Bind the request, repository revision, tenant/policy boundary, allowed side effects, and evidence requirements.
2. Select the narrowest package or child Skill; traverse package prerequisites in the compiled topological order.
3. Treat unavailable dependencies, unknown semantics, missing authorization, and missing evidence as blockers.
4. Keep blueprint import, local contract integration, runtime execution, external verification, and certification as distinct states.
5. Require the applicable repository gates and independent evidence before raising any completion or certification claim.

## Integration boundary

- This routing contract is `LOCAL_CONTRACT_IMPLEMENTED`.
- The 101 archive Skills remain `BLUEPRINT_IMPORTED` until separately implemented and evidenced.
- All 102 repository handlers are `LOCAL_IMPLEMENTED_BOUNDED`; this does not promote source, runtime, external, or certification evidence.
- Runtime and external evidence are `NOT_RUN`; certification is `NOT_CERTIFIED`.
- Archive scripts were not executed by the importer and cannot grant permissions or release authority.

## Repository Runtime

```bash
PYTHONPATH=engines/software-factory-engine/src python3 -m elmos_software_factory execute --skill elmos-7plus1-commercial-software-factory --request <file>
```

The binding is `BOUND_NOT_EXECUTED`, not runtime evidence. External actions still require explicit adapters and authorization.
