---
name: chinadb-03-rule-mutation-dsl
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Rule & Mutation DSL Engine. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "03-rule-mutation-dsl"
  source_path: "skills/03-rule-mutation-dsl/SKILL.md"
  source_sha256: "sha256:7b7f1080b5bfeefa72f407c9cbbea9b61f93eae9e3ce4e22674985747d9f7fe0"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# Rule & Mutation DSL Engine

- **Skill ID:** `03-rule-mutation-dsl`
- **Version:** `1.0.0`
- **Category:** core/rules
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Implement deterministic, version-aware conversion rules and repair mutations over Semantic IR with traceability from source construct to target code and test evidence.

## Inputs

- Semantic IR
- Source/target engine+version+mode
- Rule packs
- Risk policy
- Fixture corpus

## Required outputs

- Compiled rule graph
- Rule application trace
- Conversion decisions and risk labels
- Conflict detection report
- Mutation candidates

## Implementation modules / repository contract

- rules/dsl_schema.py
- rules/compiler.py
- rules/matcher.py
- rules/executor.py
- rules/conflicts.py
- rules/trace.py
- rules/mutations.py

## Interfaces and contracts

- Example syntax in `config/rule-dsl-example.yaml`
- Each rule declares source predicate, target semantic operation, risk and verification fixtures

## Workflow

1. Compile declarative rules and validate version ranges.
2. Order rules by semantic specificity and explicit priority.
3. Reject ambiguous same-priority rule collisions.
4. Apply transformations while attaching rule ids and source maps.
5. Generate candidate mutations for verification failures; never self-approve high-risk repairs.
6. Record every conversion decision in the evidence ledger.

## Mandatory tests

- Version boundary rules
- Conflicting rule packs
- Negative predicates
- Idempotent transformations
- Mutation rollback
- Rule trace completeness
- Malformed DSL rejection

## Required evidence

- Compiled rule-pack hash
- Rule coverage report
- Conflict report
- Per-artifact conversion trace

## Fail-closed / escalation rules

- Regex-only semantic transformations are disallowed.
- Rules with unknown target semantics must emit manual/unsupported status.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `03-rule-mutation-dsl`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
