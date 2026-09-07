# Batch 1–13 hardening and verification

Verified on macOS on 2026-07-21. This is the current repository-level closure record for the Java modernization Batches 1–10, the .NET and Python engines in Batches 11–12, and the cross-system orchestration layer in Batch 13. It does not claim that an external customer migration or production cutover occurred.

## Hardening completed

| Boundary | Result |
|---|---|
| Shared Engine API | Unconfigured generic Java `scan`, `plan`, `validate`, and `execute-step` calls terminate as `FAILED` with empty evidence and explicit `configured=false`, `executed=false`, and `customerCodeExecuted=false`. Changed-input idempotency reuse and terminal cancellation return conflicts. |
| Workflow | Migration plans reject cycles. Runs retain the approved plan, enforce exact step identity and dependency order, allow retry only after retryable failure, increment attempts, and permit validation only after every approved step succeeds. |
| Recipe governance | Execution manifests require exported data tables. Missing required tables or non-fixpoint idempotence blocks promotion. Repair verification cannot pass without evidence. |
| Independent quality | Empty evidence is `INCONCLUSIVE`, never `PASS`. Required domains, evidence references, duplicate-domain rejection, and negative comparison results are enforced independently of Recipe and Agent execution. |
| Delivery | Acceptance requires a named human. Conditional acceptance cannot close delivery. Every read-model fact needs evidence, and accepted risks require an expiring acceptance reference. |
| Enterprise and commercial | Unknown IdP groups fail closed; Runner and Secret leases are positive and capped at 15 minutes; model requests require bounded identity and budget data. Entitlements are time-bound, consumption is positive, fulfillment idempotency is tenant-scoped, and changed-input reuse conflicts. |
| .NET and Python engines | Execution idempotency fingerprints include policy, budget, workspace, configuration, and executor inputs; atomic registries prevent duplicate execution. Non-executable transformations fail closed, and HTTP submission conflicts return `409`. |
| Composite orchestration | Shadow comparisons distinguish deterministic, normalized, tolerance, approved expected-difference, regression, and not-comparable outcomes. Canary stages cannot be skipped, CDC metrics cannot be negative, and cutover requires a named approval of the frozen manifest. |
| Skills and contracts | All 35 Build Skills and 101 Runtime Skills pass the Skill Creator validator with no placeholders. All 93 JSON documents and 3 YAML contracts parse successfully. |

## Current local verification

| Gate | Result |
|---|---|
| Java/Maven reactor | 39 modules plus the parent; full `clean verify` produced 59 Surefire reports containing 241 tests, 0 failures, 0 errors, and 1 Docker-dependent skip. |
| PostgreSQL 17 | V1–V13 applied in order to a fresh temporary database: 597 public tables, 596 tenant-isolation policies, 597 `organization_id` columns, and 31 append-only trigger objects. V13 extended the existing `message_contracts` and `model_endpoints` authorities rather than duplicating them. |
| .NET 10 | 12 tests passed; `dotnet format --verify-no-changes` passed. |
| Python 3.14 | 31 tests passed; Ruff and strict mypy passed across 19 source files. |
| Web console | TypeScript and the Next.js 16.2.10 production build passed; `/` and `/_not-found` were statically generated. |
| Skills | 136 Batch Build/Runtime Skills passed `quick_validate.py`; no TODO, TBD, or placeholder marker remains. |
| Contract syntax | 93 JSON documents and 3 YAML documents parsed successfully; executable Java contract/fixture tests are included in the Maven result. |

The Maven Testcontainers Flyway test remains skipped when no Docker API is available. The direct fresh PostgreSQL run above verifies SQL execution and schema invariants, but it does not substitute for approved container-image, rootless isolation, or customer-environment evidence. The temporary database was stopped and moved to macOS Trash for recoverable cleanup.

## Completion boundary

Batch 1–13 are complete as a repository implementation with executable domain rules, contracts, persistence projections, workers, UI disclosure, Skills, fixtures, and fail-closed tests. The following remain external acceptance gates and therefore retain `NOT_CONFIGURED`, `NOT_RUN`, or `BLOCKED` rather than being reported as completed:

- a real least-privilege GitHub App installation, short-lived installation tokens, webhook delivery, immutable customer snapshot, and revocation drill;
- signed and approved rootless Runner images, default-deny egress enforcement, Vault/KMS leases, escape tests, cleanup evidence, and private/air-gapped deployment;
- real customer OpenRewrite execution, bounded Codex/Claude/OpenHands editing, fresh baseline/migrated environments, and independent behavior comparison;
- authorized PR/MR creation, provider Checks, external Ed25519 key custody, Evidence Pack verification, merge/release observation, and rollback rehearsal;
- enterprise IdP, SIEM, private Runner fleet, model providers, CRM/payment/tax/invoice/accounting systems, SLA observations, and legal-hold/deletion operations;
- Windows Legacy/IIS/COM/WCF, Python 2, GPU/CUDA, clean-kernel notebooks, production data/model assets, OpenTelemetry topology, CDC/backfill/reconciliation, shadow traffic, canary, cutover, stability-window, and decommission evidence.

No unit test, fixture, schema, plan, synthetic shadow result, or simulated demo event is represented as proof that customer code ran or that a production migration succeeded.
