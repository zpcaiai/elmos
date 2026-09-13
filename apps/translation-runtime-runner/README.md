# Hosted translation runtime boundary

The existing Java/PG execution queue owns identity, leases, cancellation, budgets
and publication. It hydrates the digest-bound tenant input object using its lease
only against the fixed control-plane origin. No lease token or object URL enters
the workload. Source/cases are mounted read-only and network is denied.

Runner starts the pinned image twice: `translate-preflight-v1`, validates the
receipt, synchronously acknowledges a fenced `pipeline` heartbeat, then starts
`translate-pipeline-v1`. Customer stdout cannot start metering. Both phases share
one wall-clock budget. The second phase reuses the Web pipeline's full report,
shard, manifest, archive and digest validators; PARTIAL remains PARTIAL.

The Dockerfile is a build contract, not deployment evidence. An operator-supplied
digest-pinned base must include `/opt/elmos/venv/bin/python`, exact route native
toolchains, Node, and locked Web dependencies (including the trusted TypeScript
loader) under `/opt/elmos/apps/web-console/node_modules`. No image digest, provider
attestation, production route evidence or deployment is supplied by this change.
Control-plane `elmos.execution.images.translation` must be an immutable verified
image, and `elmos.translation.repository-root` / `cases-root` must be trusted,
non-symlink operator paths. Missing configuration fails closed.
`elmos.translation.node-executable` must be an absolute trusted Node executable;
the fixed admission launcher reuses the exact Web route evidence gate.

After V90, an approved database operator applies the repository-owned
`modules/persistence/src/main/resources/db/provisioning/translation_input_runtime.sql`,
then explicitly grants `elmos_translation_input_runtime` to the exact configured
control-plane DB login. No LOGIN, password, automatic membership, wallet write,
private-counter read, or tenant-policy change is supplied. Unsafe pre-existing
roles are rejected. Submission/readiness checks the actual required privileges;
missing provisioning fails before source preparation or object PUT. This is an
add-on capability, not a replacement for existing control-plane service grants.

Prepared input roots reuse `content_objects`. They are never collected merely
because a presigned URL/attach deadline expired: an already-started PUT can remain
unknown. Unreconciled roots have tenant/global count and byte budgets; when full,
new preparation fails closed pending trusted operator reconciliation. Attached
inputs live through the job plus the existing tenant STANDARD retention period.
This change does not implement provider reconciliation automation.
Only a newly inserted PREPARED binding grants a PUT attempt. Reusing an unknown
preparation fails closed; an existing queued/terminal idempotent job returns
without another PUT, so one writer cannot release another writer's protection.

Hosted translation now binds to the existing canonical prepaid-wallet job
contract rather than introducing a second credit producer. The billable measure
is server-recorded runtime wall seconds: `SUCCEEDED` and `PARTIAL` settle actual
elapsed seconds up to the reservation ceiling; cancellation before start,
ordinary platform failure, and `LOST` release the hold; cancellation after start
settles measured work. Customer stdout cannot change the meter. The exact CNY
minor-unit rate, floor, reserve, effective window, and catalog version must be an
exact `PUBLISHED` `TRANSLATION/translate-pipeline-v1` price. Wildcard or `DRAFT`
prices are rejected. `ELMOS_BILLING_ENFORCEMENT_ENABLED=true` additionally
requires the database wallet switch to be enabled. Enqueue holds the billing
switch row and takes the wallet reservation in the same transaction as the job;
terminal settlement remains idempotent through the existing outbox and ledger.
Unknown pricing or settlement remains unresolved instead of being guessed.
The repository ships only a `DRAFT` example, so commercial charging stays
disabled until Finance publishes and activates an exact catalog version. Local
fixture execution is engineering evidence, not accounting or production
certification.

`test/launcher.test.mjs` runs a real Python-to-TypeScript fixture only when
`ELMOS_TRANSLATION_TEST_PYTHON` names the intended project interpreter. It retains
the fixture path on both success and failure. A later read-only replay requires no
native rebuild or provider call:

```
node --loader ./apps/translation-runtime-runner/ts-loader.mjs \
  ./apps/translation-runtime-runner/replay.mjs /absolute/retained/fixture
```

For repeatable local OCI qualification, build the digest-pinned development
base and then the runtime contract. The qualification base is deliberately not
a deployable production base or provider attestation:

```
docker build -f apps/translation-runtime-runner/Dockerfile.qualification-base \
  -t elmos/translation-qualification-base:local .
docker build -f apps/translation-runtime-runner/Dockerfile \
  --build-arg ELMOS_TRANSLATION_BASE_IMAGE=elmos/translation-qualification-base:local \
  -t elmos/translation-runtime:local .
docker image inspect elmos/translation-runtime:local --format '{{.Id}}'
engines/polyglot-route-engine/.venv/bin/python \
  tools/performance/hosted_translation_container_profile.py \
  --docker-context <context> --image-id sha256:<64-hex-image-id> \
  --jobs 4 --concurrency 2 \
  --output tools/performance/hosted-translation-container-local.json
```

Pass that immutable image ID to
`tools/performance/hosted_translation_container_profile.py`. The harness uses
non-root containers, a read-only root, no network, all capabilities dropped,
bounded CPU/memory/PIDs and read-only inputs. Its JSON remains local
self-attested evidence with production/provider/independent/certification fields
explicitly blocked.
