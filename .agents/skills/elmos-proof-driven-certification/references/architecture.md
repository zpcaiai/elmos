# Architecture

## Target Trust Chain

```text
Builder Agent
  │ VerificationRequest
  ▼
Authority
  │ immutable snapshot + VerificationTicket
  ▼
Truth Runner
  │ actual OS/tool execution
  ▼
Execution Evidence
  │ content-addressed manifest + attestation
  ▼
Immutable Evidence Store
  ├──────────────┐
  ▼              ▼
Ethen Audit      OPA Gate
  └──────┬───────┘
         ▼
Certification Gate
         │
         ▼
Signed Certification
         │
         ▼
Deployment Digest Gate
```

## Responsibility Boundaries

| Component | Owns | Must not own |
|---|---|---|
| Builder | implementation changes, public/generated tests, verification requests | certification, authoritative evidence, hidden tests, active policy, signing keys |
| Authority | snapshot identity, digests, Ticket issuance | implementation edits, execution facts, final PASS |
| Truth Runner | real execution and factual observations | source modification, final certification |
| Evidence Store | immutable content-addressed facts | semantic judgment |
| Ethen | semantic requirement audit | execution facts, code modification, PASS override |
| OPA/Gate | deterministic authorization | evidence fabrication |
| Release Gate | exact certified artifact enforcement | rebuilding/reinterpreting evidence |

## Golden Route

```text
REQUESTED
→ SNAPSHOTTING
→ SNAPSHOT_READY
→ TICKET_ISSUED
→ RUNNER_ACCEPTED
→ EXECUTING
→ EVIDENCE_COMMITTED
→ ATTESTED
→ SEMANTIC_AUDIT (when required)
→ POLICY_EVALUATING
→ PASSED | FAILED | BLOCKED
```

Illegal direct transitions include `REQUESTED → PASSED`, `EXECUTING → PASSED`, and `EVIDENCE_COMMITTED → PASSED`.

## Commit Boundary

Every authoritative external action follows:

```text
prepare → execute → intercept environment result → validate → immutable commit → return reference
```

A Builder may request an action but cannot commit a trusted result.

## Evidence Graph

```text
SOURCE DIGEST
  ↓ Snapshot
BUILD ARTIFACT DIGEST
  ↓ Build attestation
EXECUTION
  ├ Raw ToolResults
  ├ JUnit/coverage
  ├ Mutation/Sabotage
  └ Execution attestation
  ↓
SEMANTIC AUDIT ATTESTATION
  ↓
OPA DECISION
  ↓
CERTIFICATION ATTESTATION
  ↓
DEPLOYMENT OF SAME ARTIFACT DIGEST
```

Every authoritative edge must be digest-bound.
