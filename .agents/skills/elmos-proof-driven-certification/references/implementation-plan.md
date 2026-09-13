# Implementation Plan

## Phase A — Minimum Trustworthy Loop

### WP-TRUST-001 Canonical Contracts

Implement versioned DTO/domain contracts for:

- VerificationRequest
- VerificationTicket claims
- FrozenSnapshot / SubjectDescriptor
- RunnerProfile / CaseSet
- ProcessObservation / TestObservation
- ExecutionEvidence
- EvidenceManifest
- GateInput / GateDecision
- ReasonCode / VerificationStatus

Keep API contracts separate from persistence entities.

### WP-TRUST-002 Snapshot Authority

- Deterministically freeze source.
- Compute SHA-256 subject digest.
- Version the snapshot/exclusion profile.
- Store an immutable snapshot reference.
- Prevent TOCTOU by never testing the mutable Builder workspace.

### WP-TRUST-003 VerificationTicket

- Issue compact JWS with EdDSA in MVP.
- Bind source, case catalog, runner profile, policy and hidden-test digests.
- Validate issuer/audience/JTI/nonce/time claims and prevent replay.
- Do not accept Builder-defined command/expected result.

### WP-TRUST-004 Golden Truth Runner

Start with `java-spring-e3` only:

- pinned JDK + Maven environment;
- compile;
- JUnit 5 hidden/unit test;
- Spring integration test;
- HTTP smoke test;
- JaCoCo report parsing;
- ephemeral sandbox;
- direct argv execution and result interception.

### WP-TRUST-005 Evidence Append Store

- content-address stdout/stderr/reports;
- build EvidenceManifest;
- append-only evidence table/object storage;
- revoke UPDATE/DELETE from application roles;
- Builder cannot insert evidence.

### WP-TRUST-006 OPA Gate

- default deny;
- trusted Gate Service assembles input;
- required digest matches;
- required steps actually spawned/completed;
- minimum tests and zero failures;
- missing reports/infrastructure failure fail closed;
- structured reason codes.

### WP-TRUST-007 Anti-Fake Suite

All AF cases in `adversarial-cases.md` are P0 release blockers.

## Phase B — Production Identity & Provenance

In dependency order:

1. WP-TRUST-101 SPIFFE/SPIRE workload identity abstraction.
2. WP-TRUST-102 mTLS/capability enforcement.
3. WP-TRUST-103 KMS key separation/purpose enforcement.
4. WP-TRUST-104 in-toto execution attestation.
5. WP-TRUST-105 immutable/object-locked Evidence Store.

Milestone acceptance: fake Builder evidence cannot obtain trusted Runner identity, Runner signing authorization, valid execution attestation, or trusted immutable provenance.

## Phase C — Durable and Adversarial Certification

1. WP-TRUST-106 Temporal workflow.
2. WP-TRUST-107 isolated Authority/Runner/Certifier workers/task queues.
3. WP-TRUST-108 Hidden Test Vault.
4. WP-TRUST-109 Mutation engine.
5. WP-TRUST-110 Sabotage engine.

Milestone acceptance: crashes/retries cannot false-pass, Builder cannot inspect hidden tests, weak tests are exposed, known infrastructure attacks have zero certification escapes.

## Phase D — Independent Semantics and Release

1. WP-TRUST-111 Ethen independent semantic audit.
2. WP-TRUST-112 signed OPA bundles.
3. WP-TRUST-113 build attestation.
4. WP-TRUST-114 final certification attestation.
5. WP-TRUST-115 deployment digest gate.
6. WP-TRUST-116 production red-team certification.

## Definition of Done

Do not mark a WP complete from file existence. A WP needs code + tests + actual execution results + no unresolved mandatory adversarial test for its trust boundary.
