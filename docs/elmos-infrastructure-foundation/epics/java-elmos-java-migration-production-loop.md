# Production Java Modernization Closed Loop

- Skill: `elmos-java-migration-production-loop`
- Priority: `P0`
- Phase: `G6`
- Dependencies: `elmos-identity-tenant-security`, `elmos-temporal-task-reliability`, `elmos-repository-snapshot-workspace`, `elmos-content-addressed-cache`, `elmos-staging-snapshot-promotion`, `elmos-reproducible-toolchain`, `elmos-secure-sandbox-runtime`, `elmos-verification-fabric`, `elmos-evidence-pack-offline-verification`

## Objective

Make one narrow Java modernization path real and repeatable before expanding more languages/domains.

## Task groups

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

## Validation

- [ ] Complete an end-to-end fixture and three pilot repositories.
- [ ] Force-push source branch after snapshot and retain original result.
- [ ] Repeat OpenRewrite and require idempotency.
- [ ] Lose PR response and reconcile without duplicate PR.
- [ ] Interrupt runner/model/workflow and resume from checkpoints without duplicate effects.

## Exit gate

- [ ] A fixed authorized repository repeatedly produces a reviewable PR and signed offline evidence.
- [ ] Source residency, identity, sandbox, budget, verification, and audit gates are enforced.
- [ ] Failures are classified and manual gaps are explicit.
- [ ] The path is demonstrably billable rather than scaffold-only.
