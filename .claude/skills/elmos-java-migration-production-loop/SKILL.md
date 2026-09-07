---
name: elmos-java-migration-production-loop
description: Implement the first billable end-to-end path from GitHub installation
  and immutable snapshot through baseline, health analysis, OpenRewrite, verification,
  bounded agent repair, PR/checks, and evidence.
version: 1.0.0
priority: P0
phase: G6
dependencies:
- elmos-identity-tenant-security
- elmos-temporal-task-reliability
- elmos-repository-snapshot-workspace
- elmos-content-addressed-cache
- elmos-staging-snapshot-promotion
- elmos-reproducible-toolchain
- elmos-secure-sandbox-runtime
- elmos-verification-fabric
- elmos-evidence-pack-offline-verification
---

# Production Java Modernization Closed Loop

## Objective

Make one narrow Java modernization path real and repeatable before expanding more languages/domains.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Production Java Modernization Closed Loop** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-identity-tenant-security`
- `elmos-temporal-task-reliability`
- `elmos-repository-snapshot-workspace`
- `elmos-content-addressed-cache`
- `elmos-staging-snapshot-promotion`
- `elmos-reproducible-toolchain`
- `elmos-secure-sandbox-runtime`
- `elmos-verification-fabric`
- `elmos-evidence-pack-offline-verification`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- GitHub App installation tokens replace long-lived PATs.
- Source is fixed to commit and stays local by default.
- OpenRewrite/deterministic recipes execute before LLM repair.
- Customer reviews and merges the PR.
- Every failure is classified and evidenced.

## Required inputs

- Authorized GitHub/GHES installation and repository.
- Source/target Java, Spring/Jakarta, build, dependency, test, security, and delivery profiles.
- Tenant runner/source-residency/model/policy/budget settings.

## Required outputs

- `Immutable source/baseline/target snapshots.`
- `Health report and migration DAG.`
- `Idempotent recipe patches plus bounded repair patches.`
- `Compile/test/contract/security results.`
- `Idempotent PR/checks and signed evidence pack.`

## Repository discovery

Before editing:

1. Locate `AGENTS.md`, `CLAUDE.md`, repository-local Skills, architecture decision records, manifests, schemas, migrations, and build commands.
2. Identify actual control-plane, workflow, runner, engine, web, database, object-store, policy, telemetry, and test modules; do not assume the reference layout exists.
3. Search for existing contracts and implementations before creating duplicates.
4. Record current behavior, known gaps, security boundaries, external side effects, and the exact validation commands that are available.
5. Create or update a durable implementation plan from `templates/IMPLEMENTATION-PLAN.yaml`.

## Execution workflow

1. Select the smallest dependency-resolved vertical slice.
2. Freeze input snapshots, schema/toolchain/policy versions, and rollback boundaries.
3. Implement contract/schema changes before consumers, using backward-compatible transitions.
4. Implement production behavior, authorization, idempotency, telemetry, audit, failure handling, tests, documentation, and runbooks together.
5. Execute focused tests, integration tests, race/failure tests, security tests, and clean-environment reproduction as applicable.
6. Save large outputs by digest; record commands, results, durations, cost, evidence, and residual risk.
7. Report autonomous **system wall-clock runtime** separately from human-equivalent engineering/review effort.
8. Never claim production completion from generated files or static validation alone.

## Implementation checklist

### GitHub integration

- [ ] `ELMOS-JAVA-001` Sync installations/repositories and handle installation suspension/removal.
- [ ] `ELMOS-JAVA-002` Verify repository ownership by installation before access.
- [ ] `ELMOS-JAVA-003` Issue short-lived least-privilege clone and delivery tokens separately.
- [ ] `ELMOS-JAVA-004` Validate webhook signature/delivery id and handle rate limits, retry, GHES URL/API differences, and errors.
- [ ] `ELMOS-JAVA-005` Never store a long-lived PAT in project/task records.
### Snapshot and baseline

- [ ] `ELMOS-JAVA-006` Clone fixed commit with submodule/LFS/size/path policy into leased private workspace.
- [ ] `ELMOS-JAVA-007` Seal snapshot manifest/digest and enforce source-local or approved encrypted upload policy.
- [ ] `ELMOS-JAVA-008` Select signed JDK/build toolchain, validate wrappers, inject private registry secrets, and reproduce build.
- [ ] `ELMOS-JAVA-009` Record modules, dependencies, tests, artifacts, environment/code/private-registry failures, and source modifications.
- [ ] `ELMOS-JAVA-010` Capture pre-existing failures and baseline evidence.
### Health check and plan

- [ ] `ELMOS-JAVA-011` Build Maven/Gradle module graph and identify JDK, Spring, Security, Hibernate/JPA, Jakarta, testing, serialization, transaction, cache, messaging, API, database, and deployment fingerprints.
- [ ] `ELMOS-JAVA-012` Detect dependency conflicts, CVE/license candidates, unsupported plugins, reflection, native bindings, generated code, and compatibility risks.
- [ ] `ELMOS-JAVA-013` Select target profile and supported intermediate states such as Boot 2.7 to 3.x before later targets.
- [ ] `ELMOS-JAVA-014` Create dependency-aware migration DAG with deterministic probability, manual work, risk, evidence, budget, and system wall-clock ETA plus separate human-equivalent effort.
- [ ] `ELMOS-JAVA-015` Require plan review/approval before rewrite.
### Deterministic transformation

- [ ] `ELMOS-JAVA-016` Resolve a signed/versioned Recipe Catalog/BOM and license.
- [ ] `ELMOS-JAVA-017` Evaluate preconditions, dry run, affected modules/symbols, conflicts, and risk.
- [ ] `ELMOS-JAVA-018` Execute recipes in isolated staging and produce segmented thematic patches/commits.
- [ ] `ELMOS-JAVA-019` Run recipes twice and require no second diff where declared idempotent.
- [ ] `ELMOS-JAVA-020` Preserve original worktree and emit recipe execution manifest.
### Verification and long-tail repair

- [ ] `ELMOS-JAVA-021` Compile/test target and compare discovered/skipped/passed tests, APIs, contracts, dependencies, SBOM, security, and behavior against baseline.
- [ ] `ELMOS-JAVA-022` Classify failures before model use.
- [ ] `ELMOS-JAVA-023` Run repair agent only inside private sandbox with selected semantic context, tool/egress allowlist, hard budget, max iterations, and non-improvement stop.
- [ ] `ELMOS-JAVA-024` Reject test deletion, assertion weakening, security disabling, hidden exceptions, and unrelated broad changes.
- [ ] `ELMOS-JAVA-025` Escalate unresolved gaps to explicit human tasks.
### Delivery

- [ ] `ELMOS-JAVA-026` Seal validated target snapshot and build topic commits.
- [ ] `ELMOS-JAVA-027` Create/reconcile idempotent branch, PR, checks, labels, reviewers, and comments with minimal installation token.
- [ ] `ELMOS-JAVA-028` Include summary, migration plan, tests, risks, deviations, manual tasks, rollback, and evidence links.
- [ ] `ELMOS-JAVA-029` Generate and sign offline Evidence Pack and verification command.
- [ ] `ELMOS-JAVA-030` Keep customer as final merge authority and audit delivery operations.
### Repeatability and pilot

- [ ] `ELMOS-JAVA-031` Repeat the same fixed-commit migration and compare plan, deterministic patch, validation, and evidence digests.
- [ ] `ELMOS-JAVA-032` Test webhook duplication, concurrent start, runner loss, cancellation, provider error, PR response loss, and rollback.
- [ ] `ELMOS-JAVA-033` Run at least three authorized structurally different repositories before billable readiness.

## Required artifacts

At minimum, produce or update:

- Versioned contracts and schemas.
- Database migrations and compatibility/rollback notes where state changes.
- Production implementation with explicit authorization, idempotency, retries, cancellation, and failure classification as applicable.
- Unit, integration, end-to-end, race/failure, and security tests appropriate to risk.
- OpenTelemetry instrumentation, operational metrics, alerts, and runbooks for production components.
- Audit/evidence records with immutable input and output digests.
- Updated architecture and operational documentation.
- Task report based on `templates/TASK-REPORT.md`.

## Validation

- [ ] Complete an end-to-end fixture and three pilot repositories.
- [ ] Force-push source branch after snapshot and retain original result.
- [ ] Repeat OpenRewrite and require idempotency.
- [ ] Lose PR response and reconcile without duplicate PR.
- [ ] Interrupt runner/model/workflow and resume from checkpoints without duplicate effects.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] A fixed authorized repository repeatedly produces a reviewable PR and signed offline evidence.
- [ ] Source residency, identity, sandbox, budget, verification, and audit gates are enforced.
- [ ] Failures are classified and manual gaps are explicit.
- [ ] The path is demonstrably billable rather than scaffold-only.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
