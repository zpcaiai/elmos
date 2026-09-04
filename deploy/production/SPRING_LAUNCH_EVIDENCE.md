# Spring launch evidence intake

This workflow authenticates evidence produced by real staging, security,
operations, legal and design-partner work. It does not produce those outcomes,
sign for another party, deploy, approve a release, or certify the business line.

The exact receipt schema and verification rules are implemented by
`scripts/batch30/spring_launch_evidence.py`. A valid receipt binds all of the
following to the exact checked-out revision and launch profile:

- migrated customer artifact bytes and a canonical environment manifest;
- a separate CI-pinned worker `/app/app.jar` digest tied to the worker image and
  deployed revision by an image-extraction attestation (it must never be
  confused with the migrated customer artifact);
- the live worker's raw content-addressed inspect bytes and a secret-free,
  content-addressed web-console runtime attestation;
- exact application-host mount-source object identities, both services' immutable
  image IDs, entrypoints, commands, users, capabilities, networks and ports;
- the launch profile bytes as committed at the exact deployed Git revision;
- nine content-distinct gate evidence objects below an explicitly approved root;
- separate execution, independent-verifier and independent-reviewer identities;
- an execution signature and independent verification signature for every gate;
- separate release and risk approvals, plus at least two distinct design partners;
- an independent review signed after every gate, approval and partner endorsement;
- non-revoked Ed25519 keys, role-specific key ownership, expiry and freshness.

`NOT_RUN`, `UNKNOWN`, `INCONCLUSIVE`, placeholders, synthetic evidence, stale
signatures, path escapes, mutable URL-only claims, duplicate evidence, shared
actors/organizations/keys, and self-certification all fail closed.

The environment manifest must validate against
`schemas/batch30/spring-launch-environment-manifest.schema.json`. Its
`configuration_digest` is the exact `SPRING_CONFIGURATION_DIGEST` printed by
the launch validator when it reads the same `/controlled/spring/spring.env` and actual
application environment commitment used for interpolation. That commitment
contains exact key names and presence/empty state, plus only explicitly
allowlisted non-secret values; it never hashes DB, OIDC, session, provider or
API secret values into an offline guessing oracle. The manifest also binds
the independently derived worker/web effective configuration digests, exact
web environment-name inventory, seven application-host mount-source identities,
and the CI-pinned worker application artifact digest. The trust store,
controlled index and final receipt use
the other three `schemas/batch30/spring-launch-*.schema.json` contracts.

## Operator flow

Keep the trust store, private signing keys, evidence roots, environment file and
final receipt outside the repository. Public keys may be distributed to the
gate host; private keys never belong on that host.

The two environment files have deliberately separate authority. Create
`/srv/elmos/config` and `/controlled/spring` as deploy-user-owned `0700`
directories; use `/srv/elmos/config/elmos.env` and
`/controlled/spring/spring.env` respectively. The latter must contain exactly
the 20 keys in `spring-launch.env.example`.
`ELMOS_ENV_FILE` is the application service `env_file` and must contain no
Spring launch, servlet/server/management, JVM or proxy overrides.
`SPRING_ENV_FILE` is only inert gate input and Compose interpolation input; the
Spring worker has `env_file: []`, while the application overlay writes the
small exact web/worker Spring allowlist. Never merge or copy the Spring keys
into `ELMOS_ENV_FILE`.

```bash
# Validate the exact inert-data environment file used by the Spring Compose
# overlay and retain the printed SPRING_CONFIGURATION_DIGEST for the manifest.
python3 scripts/batch30/validate_spring_launch_readiness.py \
  --environment-file /controlled/spring/spring.env \
  --compose-environment-file /srv/elmos/config/elmos.env

# Validate both live application containers in memory and write only a sanitized record.
# The raw docker inspect includes env-file secrets and must never be redirected,
# copied or attached to the external evidence bundle. Docker inspect has no
# inode data, so this command must run on the Linux Docker host with permission
# to compare every source FD to /proc/<container-pid>/root/<mount-target>.
make spring-web-runtime-attestation \
  SPRING_WEB_CONTAINER=elmos-staging-web-console-1 \
  SPRING_WEB_IMAGE_DIGEST="$PINNED_WEB_IMAGE_ID" \
  SPRING_WORKER_CONTAINER=elmos-staging-java-engine-worker-1 \
  SPRING_WORKER_IMAGE_DIGEST="$PINNED_WORKER_IMAGE_ID" \
  SPRING_WEB_COLLECTOR_ID=staging-runtime-collector \
  SPRING_WEB_RUNTIME_ATTESTATION_OUTPUT=/controlled/evidence/web-console.runtime-attestation.json

# Hash bytes that already exist. This command does not create a pass claim.
python3 scripts/batch30/spring_launch_evidence.py reference \
  /controlled/evidence/staging-deployment.json \
  --evidence-root /controlled/evidence \
  --media-type application/json \
  --gate-reference

# External systems/people create the required Ed25519 envelopes. The repository
# verifier only adds the canonical receipt digest to an otherwise complete draft.
python3 scripts/batch30/spring_launch_evidence.py assemble \
  /controlled/drafts/spring-launch-draft.json \
  --output /controlled/evidence/spring-launch-receipt.json \
  --trust-store /controlled/trust/spring-trust-store.json \
  --evidence-root /controlled/evidence \
  --expected-revision "$DEPLOYED_GIT_REVISION" \
  --expected-trust-store-digest "$APPROVED_SPRING_TRUST_STORE_DIGEST" \
  --expected-environment-id spring-staging-cn-1 \
  --expected-deployment-id "$SPRING_DEPLOYMENT_ID" \
  --expected-provider private-linux \
  --expected-region cn-north-1 \
  --expected-environment-class STAGING \
  --expected-configuration-digest "$SPRING_CONFIGURATION_DIGEST" \
  --expected-application-environment-commitment-digest "$APPLICATION_ENVIRONMENT_COMMITMENT_DIGEST" \
  --expected-effective-spring-configuration-digest "$EXPECTED_SPRING_WORKER_CONFIGURATION_DIGEST" \
  --expected-effective-web-console-configuration-digest "$EXPECTED_WEB_CONSOLE_CONFIGURATION_DIGEST" \
  --expected-web-console-environment-names-digest "$EXPECTED_WEB_CONSOLE_ENVIRONMENT_NAMES_DIGEST" \
  --expected-application-mount-sources-digest "$EXPECTED_APPLICATION_MOUNT_SOURCES_DIGEST" \
  --expected-worker-application-artifact-digest "$SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST"

# The launch gate re-verifies every byte, signature, role and revision binding.
make spring-launch-gate \
  SPRING_ENV_FILE=/controlled/spring/spring.env \
  ELMOS_ENV_FILE=/srv/elmos/config/elmos.env \
  SPRING_EXTERNAL_EVIDENCE=/controlled/evidence/spring-launch-receipt.json \
  SPRING_TRUST_STORE=/controlled/trust/spring-trust-store.json \
  SPRING_TRUST_STORE_DIGEST="$APPROVED_SPRING_TRUST_STORE_DIGEST" \
  SPRING_EVIDENCE_ROOT=/controlled/evidence \
  SPRING_EXPECTED_REVISION="$DEPLOYED_GIT_REVISION" \
  SPRING_ENVIRONMENT_ID=spring-staging-cn-1 \
  SPRING_DEPLOYMENT_ID="$SPRING_DEPLOYMENT_ID" \
  SPRING_PROVIDER=private-linux \
  SPRING_REGION=cn-north-1 \
  SPRING_ENVIRONMENT_CLASS=STAGING \
  SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST="$SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST"
```

`SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST` must come from the controlled build
or CI extraction of `/app/app.jar`, bound to the same immutable worker image ID
and revision. It is not derived from `docker inspect`, the operator-authored
manifest, or the migrated customer artifact. The repository collector creates
neither a signature nor `PASSED_EXTERNAL`; independent parties still own those
records and signatures.

The mount commitment is not a path-string hash. For secret files it binds the
normalized path digest plus device, inode, type, size, mode, UID/GID, link count
and ctime. For the writable workspace and replay directories it binds the stable
device/inode/type/mode/UID/GID subset and relies on the same signed
`deployment_id` as the lifecycle epoch; normal child creation therefore does
not invalidate a receipt. Every source also binds the complete ancestor chain's
device/inode/type/mode/UID/GID; a secret's immediate parent is `10001:10001`
and `0700`, and no ancestor may be an unsafe non-sticky group/other-writable
directory. The collector compares the host object with the
object visible in each container mount namespace and then re-inspects both
container IDs/PIDs/configurations. Run it only after the canary deployment is
stable; any source replacement or container restart during collection fails
closed.

On the application host, materialize the four HMAC files only through a Secret
Manager or equivalent non-echoing controlled writer. Each must be a distinct
32..4096-byte, single-link regular file owned by `10001:10001` with mode `0400`
(temporarily `0600` during controlled rotation). Create the replay directory as
`10001:10001/0700`. The workspace path must already be a real cross-host storage
mount before its `runs` directory is set to `10001:10001/0700`; a local `mkdir`
is not evidence that Worker and Runner share storage.

`SPRING_EXPECTED_REVISION` must be the independently recorded 40-character
revision actually deployed. The production Make gate passes it explicitly; it
does not infer deployment identity from whichever checkout happens to run the
gate.

`APPROVED_SPRING_TRUST_STORE_DIGEST` is a composite digest of the strict trust
store bytes and every referenced public-key byte sequence. Pin it through an
independent deployment approval/configuration channel before receipt intake;
computing it from the same mutable file inline with the gate would not be a
trust anchor. Private signing keys are never inputs to these commands.

The maximum successful repository result remains
`EXTERNAL_EVIDENCE_INTAKE=VALIDATED_NOT_CERTIFIED` and
`CERTIFICATION=NOT_CERTIFIED`. A separate authorized release process owns any
production or certification decision.
