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
the packaged-worker smoke run are engineering evidence only. Provider
provisioning, native language toolchains, real service/browser journeys,
independent holdout, customer acceptance, SCM checks, commercial review and
production deployment remain `NOT_RUN` until separately authorized and backed
by exact immutable evidence. The highest certificate level is emitted only by
B108-S16 after the ordered ladder and cleanup prerequisites are satisfied; the
result still does not approve deployment or certify the product.
