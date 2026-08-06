# Batch 105-108 production closure

## Scope

This implementation turns the 64 immutable B105-B108 Skill contracts into one
tenant-bound, fail-closed execution path. It does not redefine the source
contracts and it does not treat local execution as external certification.

## Runtime path

1. The web console submits a typed request through its authenticated BFF.
2. The control plane derives organization and actor identity from the verified
   principal, rejects secrets in the payload, calculates a canonical digest and
   persists a `MODERNIZATION_PROOF` execution job.
3. Runner Agent leases the job and starts the digest-pinned, non-root proof
   worker with its standard read-only-source/default-deny-network sandbox.
4. The worker verifies the exact embedded 64-contract catalog, calculates the
   dependency closure and evaluates each Skill with its explicit operator.
5. Every decision is content-addressed. Missing, stale, cross-subject,
   self-verified or unsigned required evidence blocks the dependent Skill.
6. The worker atomically writes the plan and decision receipts below the
   job-confined output directory. Existing artifact persistence records the
   immutable output and exposes it only inside the authenticated tenant.
7. Cancellation is cooperative. Runtime routes are revoked before environment
   destruction, and TTL starts only after readiness.

The control plane and worker never execute an external provider operation on a
caller assertion and never accept caller supplied `PASS`, `certified`,
`destroyed` or `productionReady` flags as evidence.

## Components

- `modules/modernization-proof-loop`: typed model, exact catalog, dependency
  planner, 64 explicit Skill operators and deterministic receipts.
- `apps/modernization-proof-worker`: isolated executable worker and pinned
  container definition.
- `apps/control-plane`: contract discovery, subject digest and durable job APIs.
- `modules/persistence`: versioned `MODERNIZATION_PROOF` business-line migration.
- `apps/web-console`: authenticated no-store BFF, run/cancel/poll UI and artifact
  display.
- `client-packs/elmos-batch105-108-proof-loop-console`: UI Interaction IR,
  target profile, support matrix and independent corpus declarations.

## Configuration

The control plane refuses job admission until
`ELMOS_RUNNER_IMAGE_MODERNIZATION_PROOF` is set to an immutable image reference
containing `@sha256:<64 lowercase hex characters>`. The existing Runner Agent,
object storage, OIDC and PostgreSQL/RLS configuration remain authoritative.

The image builder distinguishes three decisions:

- `artifact_readiness` covers a clean source tree, immutable digest, image
  contract, restricted smoke execution and an authenticated Docker Scout scan.
- `production_readiness` additionally requires a non-local registry and every
  external boundary to be independently verified.
- `certified` remains the decision of a separate external authority. Neither a
  build nor a PR may set it to true.

Use `--release-candidate` only with an external registry. It fails closed unless
`--push` and `--scan` are supplied, the source tree is clean and the artifact
gate passes. Docker Scout exit code 2 is recorded as `FAILED`; authentication,
network or missing-report failures are `BLOCKED`, never a pass. Every scan uses
a new SARIF path so a failed invocation cannot reuse a previous clean report.
The builder binds the image to the same exact Git commit and checks source
cleanliness both before and after the build.

After opening a real Draft PR, collect its exact read-only observation with:

```text
python3 scripts/operations/collect_modernization_proof_release_evidence.py \
  --repository zpcaiai/elmos --pr <number> \
  --image-receipt <image-build-receipt.json> \
  --output <release-closure-receipt.json>
```

The PR head must equal the image source commit. This records the operation as
executed but awaiting independent verification; it does not self-approve,
deploy, merge or certify the candidate.

Re-evaluate both receipts without trusting their status fields:

```text
python3 scripts/operations/run_modernization_proof_release_gate.py \
  --image-receipt <image-build-receipt.json> \
  --release-closure <release-closure-receipt.json> \
  --output <release-gate-result.json>
```

The gate verifies content bindings, exact external-boundary keys and allowed
transitions, the immutable image/environment assignment, restricted smoke
evidence, authenticated vulnerability evidence, distinct executor/verifier
identities and required raw evidence roles. Its maximum local decision is
`READY_FOR_EXTERNAL_GATE`; it always emits `production_ready=false` and
`certified=false`.

Collect the final conservative status only after the real Draft PR and local
Flyway run exist:

```text
python3 scripts/operations/collect_modernization_proof_conservative_status.py \
  --image-receipt <image-build-receipt.json> \
  --release-closure <release-closure-receipt.json> \
  --primary-worktree <developer-worktree> \
  --source-worktree <clean-image-source-worktree> \
  --repository zpcaiai/elmos --pr <number> \
  --v63-surefire-xml <TEST-io.elmos.persistence.FlywayMigrationTest.xml> \
  --v63-surefire-text <io.elmos.persistence.FlywayMigrationTest.txt> \
  --v63-migration <V63__modernization_proof_execution_jobs.sql> \
  --v63-test-source <FlywayMigrationTest.java> \
  --evidence-directory <artifact-directory> \
  --output <release-gate-result.json>
```

The collector re-runs the gate instead of trusting the previous result. It
records the primary and isolated worktrees separately, binds the V63 report to
the migration, test source and exact PostgreSQL image digest, and observes the
current PR checks. A CI result is `PASSED` only when the rollup is non-empty and
every check succeeded. Failures and still-running checks are counted
separately. V63 success is explicitly scoped to `LOCAL_ENGINEERING_INTEGRATION`
with `production_equivalent=false`, `promotes_external_boundary=false` and
`certifies_release=false`.

## Local qualification

```text
bash skills/elmos-batch105-108/validate.sh
mvn -pl modules/modernization-proof-loop,apps/modernization-proof-worker -am test
mvn -pl apps/control-plane -am test
cd apps/web-console && npm exec tsc -- --noEmit
cd apps/web-console && npm run build
cd apps/web-console && npx playwright test e2e/modernization-proof.spec.ts --config=playwright.proof-loop.config.ts
```

The packaged worker smoke input is
`apps/modernization-proof-worker/src/test/resources/request.json`. With no
external evidence it must produce a valid `BLOCKED` result rather than a false
success.

## Evidence boundary

Source validation, Java tests, TypeScript compilation, local browser tests and
the packaged-worker smoke run are engineering evidence only. Every image build
starts all six external boundaries at `NOT_RUN`. A separate closure receipt may
advance only a boundary that was really observed; for example, an existing
Draft PR becomes `EXECUTED_AWAITING_INDEPENDENT_VERIFICATION` and must not be
rewritten to `NOT_RUN`. Provider provisioning, native language toolchains, real
service/browser journeys, independent holdout, customer acceptance, commercial
review and production deployment remain `NOT_RUN` until separately authorized
and backed by exact immutable evidence. The highest certificate level is
emitted only by B108-S16 after the ordered ladder and cleanup prerequisites are
satisfied; the result still does not approve deployment or certify the product.
