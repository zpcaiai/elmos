# Build-cache parity v1.2 runbook

## Safe default

The checked-in profile is observation-only:

```yaml
parity:
  enabled: true
  claim_mode: measured_only
  rollout_phase: observe
```

Provider-prefix serving, environment restoration, affinity serving and the
multi-layer coordinator are disabled. Keep them disabled until an evidence-
bound rollout decision explicitly advances the phase.

## HTTP trust boundary

`wsgi_app` accepts identity only from a trusted mTLS gateway middleware. The
middleware must inject an `AuthenticatedHttpContext` object at the WSGI
`elmos.authenticated_context` key. A missing or untyped context is rejected;
an authenticated tenant differing from the control-plane tenant is denied.
HTTP `Authorization` and tenant headers are not identity sources and must never
be translated into this object by application or repository code. The OpenAPI
contract declares the global `gatewayMutualTLS` boundary.

## Local inspection

From `engines/build-cache-engine/`:

```bash
elmos-cache --project <project-id> parity status
elmos-cache --project <project-id> cache explain <request-id>
elmos-cache --project <project-id> environment inspect <snapshot-key> \
  --trust-namespace <trust-namespace> \
  --transfer-ms <measured-ms> --decompression-ms <measured-ms> \
  --verification-ms <measured-ms> --rebuild-ms <measured-ms> \
  --minimum-savings-ms <policy-ms> --maximum-restore-ratio <0-to-1>
elmos-cache --project <project-id> parity report <report-id>
```

Environment inspection verifies the canonical manifest in CAS, tenant-bound
artifact references and every layer before reporting the caller-supplied
restore economics. Do not substitute metadata-only inspection or invented
timings.

Evaluation commands are read-only unless `--persist` is present:

```bash
elmos-cache prompt compile --input prompt.json
elmos-cache prompt diff --previous previous.json --current current.json
elmos-cache affinity decide --input affinity-request.json
elmos-cache parity evaluate --input measurements.json
```

For an authorized durable write, add both `--persist` and a unique exact
`--idempotency-key`. Reusing the key with a different document is an error.
Never place prompt text, source text or secret values in metadata identifiers.

## Narrow local verification

Run after shared-resource coordination permits it:

```bash
PYTHONPATH=src pytest -q \
  tests/test_prompt_cache.py tests/test_prompt_tools.py \
  tests/test_context_ledger.py tests/test_context_compaction.py \
  tests/test_environment_cache.py tests/test_environment_service.py \
  tests/test_affinity.py tests/test_coordinator.py \
  tests/test_miss_diagnostics.py tests/test_parity_runtime.py \
  tests/test_parity_store.py tests/test_parity_harness.py \
  tests/test_parity_api.py tests/test_parity_cli.py tests/test_parity.py \
  tests/test_parity_contract_assets.py tests/test_contracts_and_config.py

ruff check src tests
mypy src/elmos_build_cache
```

Run the package importer regression separately from repository root:

```bash
pytest -q tests/build-cache-staging-parity/test_import_build_cache_parity_skills.py
python3 tooling/import_build_cache_parity_skills.py --check
```

Record the exact command, source/config digests, environment, total
pass/fail/skip counts and raw log digest. Do not sum overlapping development
runs into a qualification total.

## Environment corruption or revoke

1. Stop selecting the snapshot for new restores.
2. Verify every referenced CAS layer digest and tenant/project/trust scope.
3. On corruption, quarantine the CAS object and append a `QUARANTINED` status
   event. Do not mutate the immutable manifest.
4. On policy or provenance withdrawal, append `REVOKED`. Revocation is one-way.
5. Rebuild under a new exact key only after the input identity is complete.
6. Preserve the previous manifest/status/event chain for audit.

## Miss investigation

1. Retrieve the content-free outcome by request id.
2. Inspect the closed reason family and first differing identity dimension.
3. Compare prompt/provider/model/tool profile, snapshot, ActionKey and trust
   scope in that order.
4. Treat `UNKNOWN`, missing observations and storage failure as non-success.
5. Fix identity or instrumentation. Do not broaden compatibility, suppress a
   dimension or convert an unknown into a hit.

## External parity gate

A real parity run needs the exact 20-scenario corpus and all required raw
evidence roles. Each scenario binds source, configuration, provider/SDK/model/
tool profile, date, platform, authorization, replay command, executor and a
separate verifier. Development, negative, holdout and representative corpora
remain independent.

Missing, timed-out, blocked or unverifiable evidence stays `NOT_RUN`. The local
maximum is `READY_FOR_EXTERNAL_GATE`; the repository never emits
`CERTIFIED`. Do not advance observe → shadow → canary → progressive unless
the measured report permits it. A false, cross-tenant, corrupt or
under-validated hit triggers immediate rollback.

## Resource boundary

Full pytest, Maven, Docker, package builds and other large matrices must follow
the active shared-resource coordinator. Narrow read-only checks and the slices
above are not permission to interrupt or duplicate another task's long run.
