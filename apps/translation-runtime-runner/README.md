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

After V88, an approved database operator applies the repository-owned
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

Legacy credit pricing and canonical wallet pricing differ. Until an approved
host-owned billing adapter exists, setting `ELMOS_BILLING_ENFORCEMENT_ENABLED=true`
refuses hosted translation. It never silently substitutes or double-charges.
The database wallet switch is checked too, with a shared row lock through enqueue;
an enabled wallet also refuses this unapproved translation pricing contract.
Local fixture execution is engineering evidence, not production certification.

`test/launcher.test.mjs` runs a real Python-to-TypeScript fixture only when
`ELMOS_TRANSLATION_TEST_PYTHON` names the intended project interpreter. It retains
the fixture path on both success and failure. A later read-only replay requires no
native rebuild or provider call:

```
node --loader ./apps/translation-runtime-runner/ts-loader.mjs \
  ./apps/translation-runtime-runner/replay.mjs /absolute/retained/fixture
```
