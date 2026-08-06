# Precision Migration B01-B44 runtime closure

The immutable source package under `skills/precision-migration-skills-batch-01-44/`
contains 44 Batches and 587 child Skill contracts. ELMOS installs them as a
separate `precision-migration-b01-44` namespace:

- 587 child Runtime Skills (`pm-bXX-*`)
- 44 Batch orchestrators
- 1 global workspace entrypoint: `$pm-precision-migration-orchestrator`
- 632 digest-bound Runtime Skills in total
- all 632 aliases mirrored under `.agents/skills/` for direct repository Codex discovery

`tooling/integrate_precision_migration_batch1_44.py` performs deterministic,
collision-safe installation. It preserves source identities and hashes, adds
Codex UI metadata, generates one exact adapter record per Skill, and refuses to
overwrite an unowned Runtime Skill. All 632 identities are now `LOCAL_EXECUTED`:
536 generated child handlers have unique entrypoints and immutable v4 typed
execution programs, 51 child handlers retain specialized implementations, and
the remaining 45 identities execute digest-bound orchestration DAGs with plan,
full-child preflight, and isolated child-execution modes.

## Functional loop

Use the runtime to resolve either a source identity or installed alias, derive
the mandatory assessment-to-release plan, and evaluate a request:

```bash
python3 scripts/precision_migration/runtime.py resolve \
  --skill java-to-python-direction-pack

python3 scripts/precision_migration/runtime.py plan \
  --skill pm-b16-java-to-python-direction-pack

python3 scripts/precision_migration/runtime.py evaluate \
  --request /absolute/path/request.json \
  --output-dir /absolute/path/evidence-bundle \
  --evidence-root /approved/evidence/root \
  --trust-store /approved/trust-store.json

python3 scripts/precision_migration/adapters.py execute \
  --request /absolute/path/request.json \
  --output-dir /absolute/path/adapter-output \
  --evidence-root /approved/source/root
```

Evaluation produces `skill-result.json`, `evidence-manifest.json`,
`semantic-loss-ledger.json`, and `release-gate.json`. PASS requires an actual
file or CAS object below an approved root, matching bytes/SHA-256, replay and
environment metadata, separate executor/verifier, and a scoped Ed25519
authorization. Proofs and high-risk approvals use separate signed roles with
expiry, revocation and request binding. The adapter dispatcher accepts only
generated allowlisted handlers; request or repository content cannot select a
command. Each generated program pins its algorithm, workflow, native-tool plan,
gate policy, artifact name, media type, and write-once policy at generation
time; runtime Batch/name inference is forbidden.

The remaining 557 non-B16 child Skills also have immutable external execution
profiles in `external-execution-profiles.json`. Profiles distinguish real
compiler/database/device toolchains from domain, repository, evidence, and
cutover runtimes; they never label an inapplicable compiler build as a pass.
Every profile requires native source and target execution, an independently
partitioned holdout, and an authorized representative customer workload before
external verification. The production operation runtime accepts only an
externally signed adapter registry, digest-pinned executable, typed argv,
content-addressed inputs, and scoped authorization. Mutating Canary operations
add idempotency, monotonic fencing, a registered rollback adapter, independent
approval, and `UNKNOWN` reconciliation for ambiguous outcomes.

The repository also generates an exact 2,785-case engineering suite for those
557 profiles: five actual handler invocations per Skill for positive source
fixture, target integration fixture, fail-closed negative, locally partitioned
holdout, and engineering representative fixture behavior. A separate release
drill executes disposable Ed25519 signing and verification, digest-pinned
adapter execution, injection rejection, signed Canary and registered rollback,
and an ephemeral external-certificate chain. Results are explicitly
`LOCAL_ENGINEERING_SIMULATION`, `production_eligible=false`; they never replace
native toolchain, independent-party, customer, HSM, production, or certification
evidence.

The authenticated Web Console API exposes durable tenant-isolated jobs:

- `POST/GET /api/precision-migration/jobs`
- `GET/POST/DELETE /api/precision-migration/jobs/{jobId}`
- `GET /api/precision-migration/jobs/{jobId}/artifacts/{artifact}`
- `POST /api/precision-migration/jobs/gc` for recoverable retention archives

Jobs enforce active/retained/storage quotas, cooperative cancellation, new-ID
retry, exact job-confined downloads, and hash-chained audit events.

## Status and evidence boundary

Valid runtime results are `PROVED`, `VERIFIED`, `CONDITIONALLY_VERIFIED`, `REQUIRES_ADAPTER`,
`REQUIRES_HUMAN_REVIEW`, `UNSUPPORTED`, and `FAILED`. `PROVED`
requires a signed bounded-core machine-proof record with pinned solver,
version, options, assumptions, input, and bounds. Skill maturity separately
uses `SPEC_ONLY` through `CERTIFIED`; no transition may be skipped. Local evaluation can
prepare at most `READY_FOR_EXTERNAL_GATE`; it cannot authorize production or
issue certification.

Current external source/target, independent holdout, representative workload,
shadow/canary, security review, customer acceptance, and production evidence is
`NOT_RUN`. Production certification is `NOT_CERTIFIED`.

Code-owned external workflow validation is available without promoting those
states:

```bash
python3 scripts/precision_migration/external.py validate-profiles
python3 tooling/generate_precision_migration_external_engineering_cases.py --check
python3 scripts/precision_migration/qualify_external_engineering.py --check
python3 scripts/precision_migration/production_runtime.py \
  --request /authorized/operation.json \
  --adapter-registry /authorized/signed-adapters.json \
  --trust-store /authorized/trust-store.json \
  --evidence-root /approved/evidence \
  --ledger /durable/precision-operations.sqlite3 \
  --output-dir /write-once/raw-receipts
python3 scripts/precision_migration/external.py evaluate \
  --campaign /authorized/external-campaign.json \
  --trust-store /authorized/trust-store.json \
  --evidence-root /approved/evidence
```

The external gate validates exact 557-Skill aggregate manifests, disjoint
development/holdout/representative corpora, source and target receipts,
executor/verifier separation, customer consent and purpose binding, production
HSM attestations, approved Canary evidence, exercised or actual rollback, and
an independently signed certificate. Only a complete real chain can return
`CERTIFIED`; the checked-in state remains `NOT_READY / NOT_CERTIFIED`.

## Validate

```bash
make precision-migration-b01-44-check
make precision-migration-b01-44-qualification
```

`scripts/precision_migration/run_production_code_gate.py` is included in the
official check. Its maximum decision is `READY_FOR_EXTERNAL_GATE`; a pass means
the checked-in production code surface is closed and digest-bound, not that an
external provider, customer, HSM, Canary, production operation, or certification
has run.

The installed identities and evidence boundary are recorded in
`installed-manifest.json`; handler declarations are in `adapter-registry.json`,
exact implementation profiles are in `handler-implementations.json` and
`orchestrator-implementations.json`, external production profiles are in
`external-execution-profiles.json`, and the multidimensional 587-Skill report is
in the Batch 35 verification pack. Generated engineering cases and fresh
execution bindings are in `external-engineering-qualification/cases.json` and
`external-engineering-qualification/results.json`; authoritative external state
remains separately isolated in `external-readiness/current.json`.
