---
name: chinadb-15-evidence-ledger-reproducibility
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Evidence Ledger & Reproducibility. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "15-evidence-ledger-reproducibility"
  source_path: "skills/15-evidence-ledger-reproducibility/SKILL.md"
  source_sha256: "sha256:0b67ffffcf0cebf1a26ae5410a1aa5709a1067895e3059278daf0d4640ed74ba"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
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

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `15-evidence-ledger-reproducibility`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
