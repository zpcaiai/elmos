# Batch 1–4 verification and external gates

This document covers the Java modernization foundation batches. The separately numbered polyglot translation pipeline is described in the root README and its own ADRs.

## Repository-verifiable implementation

| Batch | Implemented boundary | Fail-closed rule |
|---|---|---|
| 1 — foundation and workflow | Java 21 Maven reactor, modular-monolith boundaries, shared Engine API, immutable domain identifiers, migration plan/run/step state machines, Evidence/Audit/Outbox models, Flyway V1, and an explicitly simulated `/api/v1/demo-runs` sample | The demo is labelled `simulated`; it is not customer execution evidence. A migration run cannot validate until every approved plan step has succeeded with evidence. |
| 2 — secure source and workspace | GitHub App JWT and installation-token broker, webhook verification/idempotency, deterministic content-addressed snapshot archive, secret lease, rootless Docker workspace API, digest approval, default-deny egress policy, Flyway V2 | Personal tokens, mutable source, host execution, Docker socket exposure, unapproved images, unleased secrets, or undeclared egress cannot become an executable workspace. |
| 3 — legacy health baseline | Bounded Java/Maven/Gradle/Spring static discovery, secure XML parsing, dependency and OSV findings, baseline evidence model, `/engine/v1/health-checks`, Flyway V3 | Static discovery is not a successful build. Missing workspace/build/runtime evidence stays `NOT_RUN`, `BLOCKED`, or `INCONCLUSIVE`. |
| 4 — migration planning | Evidence-bound source/target profiles, deterministic DAG and dependency ordering, estimates, compatibility/risk gates, plan approval, `/engine/v1/migration-plans`, Flyway V4 | An unapproved, cross-tenant, cross-snapshot, wrong-version, cyclic, invented, duplicated, or dependency-out-of-order step is rejected. Plans do not prove execution. |

The generic shared Java endpoints `/engine/v1/scan`, `/plan`, `/validate`, and `/execute-step` are contract façades. Until an approved backend is bound, they return a tenant-scoped terminal `FAILED` job with empty `evidenceRefs`, `configured=false`, `executed=false`, `customerCodeExecuted=false`, and a machine-readable `reasonCode`. Reusing an idempotency key with different input returns `409`; cancelling a terminal job also returns `409`. The evidence-bound health and planning endpoints remain separate.

## Local verification

Run:

```bash
mvn -B -pl apps/java-engine-worker -am test
mvn -B -pl modules/architecture-tests -am test
```

These checks cover domain transitions, plan identity and dependency enforcement, snapshot determinism, GitHub App/token policy, default-deny boundaries, static health and planning, Engine API compatibility, tenant-scoped idempotency, and architectural separation. The current full-repository result is recorded in `docs/batch-1-13-hardening.md` after every hardening run.

## Required live acceptance sequence

1. Install a least-privilege GitHub App on a non-production private repository; prove short-lived token issuance, revocation, webhook replay rejection, and audit correlation.
2. Capture the exact commit into an immutable archive; independently verify content hash, excluded paths, submodule/LFS policy, retention, and source provenance.
3. Build and approve digest-pinned rootless sandbox images with SBOM, signature, provenance, vulnerability and secret-scan evidence.
4. Execute workspace escape, Docker-socket, privilege escalation, filesystem, resource-limit, secret-leak and undeclared-egress tests. Record cleanup and lease expiry.
5. Run the real source baseline in its compatible environment, preserving existing failures by name. Then generate and obtain named human approval for a snapshot-bound migration plan.
6. Bind the approved plan to the approved Runner. Prove that an altered snapshot, plan version, step definition, idempotency input, or dependency order is refused.

Until all relevant live steps pass, Batch 1–4 are complete only at repository implementation and fail-closed contract level, not as proof of a customer migration or production-ready Runner fleet.
