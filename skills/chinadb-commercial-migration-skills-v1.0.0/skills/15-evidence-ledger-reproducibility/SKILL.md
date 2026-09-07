# Evidence Ledger & Reproducibility

- **Skill ID:** `15-evidence-ledger-reproducibility`
- **Version:** `1.0.0`
- **Category:** core/evidence
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Provide immutable, content-addressed evidence for every conversion, test, repair, benchmark, rehearsal and certification decision so commercial delivery is auditable and repeatable.

## Inputs

- Tool/run metadata
- Generated code hashes
- Test/benchmark logs
- Route/version fingerprints
- Approval records

## Required outputs

- Content-addressed evidence store
- Evidence index
- Lineage from source artifact -> rules -> target artifacts -> tests -> gates
- Reproduction command manifest

## Implementation modules / repository contract

- evidence/model.py
- evidence/store.py
- evidence/hash.py
- evidence/lineage.py
- evidence/redact.py
- evidence/reproduce.py

## Interfaces and contracts

- Schema: `schemas/evidence.schema.json`

## Workflow

1. Hash inputs, tool versions, rule packs and generated artifacts.
2. Redact secrets while preserving integrity metadata.
3. Store evidence with immutable ids and parent links.
4. Attach evidence ids to conversion-result and repair-plan objects.
5. Generate exact reproduction commands/environment manifests.
6. Detect stale evidence when dependencies change.

## Mandatory tests

- Changed rule pack invalidates old conversion evidence
- App patch invalidates affected behavior tests
- Redaction does not alter critical result fields
- Duplicate run de-duplication

## Required evidence

- Evidence DAG
- Reproduction manifest
- Integrity verification report

## Fail-closed / escalation rules

- A screenshot or prose claim alone is not machine-verifiable evidence.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
