# Live Workbench production runbook

## Runtime topology

The Web Console calls `/api/live-workbench/**`. Its Node.js BFF validates the
account session, removes browser cookies from the upstream request, and forwards
the server-held access token to the Java control plane. The control plane derives
tenant, account, actor, environment, and authorities only from a verified JWT.
PostgreSQL RLS repeats the tenant boundary. External source, sandbox, DAP,
preview, cleanup, and private-assessment effects cross `SandboxProviderPort`.

Required bearer-token scopes are:

- `workbench.session.create`, `workbench.session.read`, `workbench.session.terminate`
- `workbench.source.read`, `workbench.debug.inspect`, `workbench.debug.control`
- `workbench.learning.read`, `workbench.learning.attempt`
- service identities only: `workbench.catalog.write`, `workbench.runtime.commit`, `workbench.runtime.event`

The browser BFF does not route catalog writes, readiness commits, or runtime
event ingestion.

## Required configuration

The Java service fails startup without the database and OIDC settings:

```text
ELMOS_WORKBENCH_DATABASE_URL=jdbc:postgresql://database:5432/elmos_workbench
ELMOS_WORKBENCH_DATABASE_USER=<secret-backed identity>
ELMOS_WORKBENCH_DATABASE_PASSWORD=<secret-backed value>
ELMOS_OIDC_ISSUER_URI=https://identity.example.com/
```

The provider remains fail-closed until all of these are configured:

```text
ELMOS_SANDBOX_PROVIDER_BASE_URI=https://sandbox-control.example.com/
ELMOS_SANDBOX_PROVIDER_SIGNING_KEY_FILE=/var/run/secrets/elmos/provider-hmac
ELMOS_SANDBOX_PREVIEW_ORIGINS=https://preview.example.com
```

The key file must be absolute, regular, non-symlinked, 32-4096 bytes, and not
group/other writable or world-readable. The Web Console requires
`ELMOS_LIVE_WORKBENCH_BASE_URL`; production uses HTTPS, while the exact internal
HTTP authority `live-workbench:8092` is permitted only when
`ELMOS_TRUSTED_INTERNAL_HTTP=true`.

## Provider contract

The provider must implement the signed `/v1/workbench/health` readiness probe,
`/v1/workbench/admission`, session allocation,
allocation-outcome cleanup by control-session id, debug dispatch and
reconciliation, cleanup, preview-access tickets, source selection, assessment,
and assessment reconciliation. Requests carry an idempotency key, timestamp,
body digest, and HMAC. Side-effect timeouts are `UNKNOWN`, never implicit
failure or success. Provider resource names must be idempotent by the supplied
control-session identity.

Preview access tickets must use an allowlisted HTTPS origin, bind the actor or
account audience, and expire no later than the committed session deadline.
Readiness is a service-to-service callback and starts exactly one 600-second
window. The reaper claims cleanup work with PostgreSQL row locks plus a bounded
claim lease, so replicas can recover abandoned cleanup safely.

## Build and local qualification

```sh
make live-workbench
pnpm --dir apps/web-console test:live-workbench-route
pnpm --dir apps/web-console build
mvn -B -pl modules/live-workbench -am package
```

`modules/live-workbench/Dockerfile` uses digest-pinned Java 21 build and runtime
images and runs as UID/GID 10001. Image building, registry signing, deployment,
provider execution, and browser/device evidence are separate external steps.

## Rollout and rollback

1. Apply the additive Flyway migration and validate RLS with a non-superuser.
2. Register qualified runtime profiles, then immutable deliveries and evidence.
3. Deploy the control plane with provider creation disabled; verify OIDC,
   database, probes, audit/outbox consumption, and cleanup reconciliation.
4. Enable one qualified Node or Python route for a bounded tenant cohort.
5. Run all 18 deployment cases, including a real 600-second window and teardown.
6. Submit the digest-bound evidence bundle to the independent certification
   authority before production promotion.

To roll back, first reject new session creation, wait for or force every active
session into cleanup, verify all resource members are `CLEANED` or explicitly
`QUARANTINED`, then remove the Web Console route and application deployment.
Do not roll back the additive database migration while audit/evidence retention
obligations remain.

## Evidence boundary

Run `python3 scripts/live_workbench/run_production_gate.py`. The checked-in
`production-evidence.json` intentionally contains `NOT_RUN`; it must not be
edited to `PASSED` without immutable raw evidence, exact environment and
revision digests, authorization, separate executor/verifier identities, and an
independent signed approval. The repository gate can produce
`READY_FOR_EXTERNAL_CERTIFICATION`; it never self-issues certification.
