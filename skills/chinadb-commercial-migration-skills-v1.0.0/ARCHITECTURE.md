# Reference Architecture

## Core execution graph

```text
Source DB + App Repos
        |
        v
Inventory / Assessment
        |
        v
Source AST + Catalog Resolution
        |
        v
Semantic DB IR  <---- Application DB Call IR
        |
        +--> Rule / Mutation DSL
        |
        +--> DDL Engine
        +--> SQL Engine
        +--> PL/T-SQL Strategy Engine ----> Lift-to-App IR
        |                                      |
        |                                      v
        |                               App Refactor Adapters
        v
Target Adapter ----> Target DB
        |               |
        |               +--> catalog / plan / error / ops probes
        v
Data Movement + CDC
        |
        v
Differential Runtime (E2/E3)
        |
        +--> Repair Loop ----> rerun affected gates
        |
        v
Performance Runtime (E4)
        |
        v
Rehearsal / Rollback / Security (E5)
        |
        v
Production Certification
```

## Route key

Every rule, result and certificate is keyed by:

`source engine + source version + source session semantics + target engine + target version + target compatibility mode + rule-pack hash + application build hash + target config hash`

Changing any route-significant key invalidates affected evidence automatically.

## Strategy taxonomy

- `NATIVE`: target supports construct with verified semantics.
- `REWRITE`: target supports equivalent behavior through transformed SQL/DDL/procedural code.
- `LIFT_TO_APP`: database logic is moved to application/event/scheduler code with updated call sites and tests.
- `EMULATE_WITH_APPROVAL`: target lacks native semantics and an emulation is accepted only through human risk approval.
- `UNSUPPORTED`: no safe automated path; migration is blocked or manually redesigned.

## Target adapter protocol

A target adapter must implement:

- `discover(target) -> CapabilitySnapshot`
- `render(ir, capability_snapshot) -> ConversionResult[]`
- `apply(artifacts, sandbox_target) -> ApplyResult`
- `introspect(target) -> CatalogSnapshot`
- `map_error(target_error) -> StableErrorContract`
- `capture_plan(sql) -> PlanIR`
- `movement_hooks() -> MovementProviderCapabilities`
- `operational_checks() -> OperationalEvidence`

No renderer may claim a feature that is absent from its capability snapshot.

## Source adapter protocol

- `discover(source) -> SourceFingerprint`
- `extract_catalog() -> CatalogGraph`
- `parse(definition) -> AST`
- `to_ir(ast, symbols, semantics) -> SemanticIR`
- `capture_workload() -> WorkloadCorpus`

## Verification invariant

A converted artifact is accepted only when its required evidence path is satisfied. Static compilation alone is never sufficient for behavior-critical SQL/procedural/application code.
