# ETGB v1.1 external qualification runbook

This runbook explains how authorized external owners can move the ETGB v1.1
release gate from `BLOCKED / NOT_CERTIFIED` to the highest state the
repository is allowed to emit:
`PROMOTE / EXTERNAL_ATTESTED_NOT_A_PRODUCTION_RELEASE`.

The repository never issues a production certificate. A separate certification
authority must review the promoted evidence and issue, reject, expire, or revoke
its own decision.

## Scope and present boundary

The release profile contains 46,664 cases and 131,452 exact
`(case_id, seed)` case-runs. Four cases are bounded local checks. The remaining
46,660 cases and 131,448 case-runs require one of seven signed external Harness
adapters.

| External adapter | Cases | Case-runs |
| --- | ---: | ---: |
| `external-dual-database-harness` | 11,760 | 35,280 |
| `external-fault-injection-harness` | 800 | 800 |
| `external-project-evolution-harness` | 200 | 200 |
| `external-project-generation-harness` | 1,100 | 3,300 |
| `external-repository-translation-harness` | 29,534 | 88,602 |
| `external-requirement-reasoning-harness` | 150 | 150 |
| `external-transformation-harness` | 3,116 | 3,116 |
| **Total** | **46,660** | **131,448** |

`READY_FOR_EXTERNAL_GATE` means the local control plane is ready to receive
external evidence. It does not mean any external case ran, any corpus was
approved, or any release was certified.

## Required owners and separation of duties

Assign durable identities before creating credentials or running a case.

| Role | Responsibility |
| --- | --- |
| Release owner | Selects the immutable source commit and candidate inputs |
| Code owner | Approves repository and runbook changes |
| Harness administrator | Configures endpoints, CA/mTLS and secret references |
| Harness executor | Executes the exact plan and signs adapter responses |
| Corpus legal reviewer | Reviews the 17 locked repositories and signs decisions |
| QA reviewer | Reviews completeness, oracles and replayability |
| Security reviewer | Reviews isolation, credentials, data and residual risk |
| Independent verifier | Replays and signs the exact release evidence subject |
| Production environment owner | Authorizes environment, data and cleanup |
| Certification authority | Issues the external production decision |

The Harness executor and independent verifier must be different identities.
The release owner and independent approver must be different identities. A
caller-provided role name is not authorization; use the organization's trusted
identity, policy, approval, and audit systems.

Copy
[`external-qualification/role-assignments.template.json`](external-qualification/role-assignments.template.json)
to an access-controlled external record and fill it there. Do not commit the
completed record.

## Secure filesystem layout

The following paths are examples of administrator-owned mounts. Set owner-only
permissions and use the production secret manager. Private signing keys and
bearer tokens must never be written to this repository.

```text
/secure/etgb/
  candidate-input.json
  frozen-candidate.json
  harness-config.json
  harness-public-trust-store.json
  release-public-trust-store.json
  license-reviews.jsonl
  role-assignments.json
  production-authority.json
  independent-attestation.json
```

The repository writes run state and evidence under a tenant/project/run-scoped
artifact root such as `.elmos/etgb/release/<candidate-digest>/`. Back it with
durable encrypted storage; do not share state databases between shards.

## Phase 1: freeze the real candidate

Copy
[`external-qualification/candidate-input.template.json`](external-qualification/candidate-input.template.json)
to `/secure/etgb/candidate-input.json` and replace every `null` with a real,
immutable value. Required fields are:

- exact 40-character source commit;
- model and immutable model revision;
- SHA-256 prompt, Skill manifest, and rule bundle digests;
- immutable toolchain image digest, never a mutable image tag;
- exact oracle and normalization versions.

Freeze the candidate:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . freeze-candidate /secure/etgb/candidate-input.json \
  --output /secure/etgb/frozen-candidate.json
```

Record the emitted `candidate_digest`. Do not edit a frozen candidate. Any
candidate input change requires a new candidate, plan, run, evidence set, and
attestation.

## Phase 2: obtain 17 independent corpus decisions

Generate the unsigned, commit-bound review request:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . corpus-review-request \
  --output .elmos/etgb/corpus-review-request-v11.json
```

An independent legal reviewer must inspect each locked repository at its exact
commit, including project license files, repository prose, dependency and
redistribution implications, patent/trademark scope, data and export controls.
Automated license detection is intake evidence, not a legal conclusion.

Each returned JSONL record must have record type `license-review`, an approved
payload bound to the exact `corpus_id`, repository, and commit, an independent
issuer identity, an expiring Ed25519 signature, and a purpose-authorized public
key in the release trust store. The shape is shown in
[`external-qualification/license-review-record.template.json`](external-qualification/license-review-record.template.json);
the template itself is invalid gate input.

Verify all records:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . corpus-review-verify \
  --records /secure/etgb/license-reviews.jsonl \
  --trust-store /secure/etgb/release-public-trust-store.json \
  --output .elmos/etgb/corpus-review-verification.json
```

Proceed only when `approved=17`, `unapproved=0`, and `valid=true`.

## Phase 3: configure the seven signed Harness services

Start from
[`harness-config.example.json`](harness-config.example.json), replace all
`.example.invalid` endpoints, and point `trust_store` to the administrator's
public trust store. Configure all seven token environment variables through the
secret manager:

- `ETGB_TRANSLATION_TOKEN`
- `ETGB_REPOSITORY_TOKEN`
- `ETGB_GENERATION_TOKEN`
- `ETGB_EVOLUTION_TOKEN`
- `ETGB_REASONING_TOKEN`
- `ETGB_DATABASE_TOKEN`
- `ETGB_FAULT_TOKEN`

Every endpoint must use HTTPS, declare an exact executor identity, reject
redirects, enforce tenant/project/authority bindings and return an expiring,
purpose-bound Ed25519 `adapter-execution` record. Use an explicit CA bundle
and mTLS where required. Keep private worker keys inside the worker's HSM, KMS,
or secret manager.

The public trust-store structure is documented by
[`external-qualification/public-trust-store.template.json`](external-qualification/public-trust-store.template.json).
Its empty key list deliberately fails preflight.

Each administrator-supplied public key record has this shape:

```json
{
  "key_id": "<stable-key-id>",
  "algorithm": "ed25519",
  "status": "active",
  "record_types": ["adapter-execution"],
  "public_key": "<base64url-encoded-32-byte-public-key>",
  "not_before": "<ISO-8601 timestamp>",
  "not_after": "<ISO-8601 timestamp>"
}
```

License-review keys use `record_types: ["license-review"]`. Never place a
private key in a trust store.

Run structural preflight:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . harness-preflight \
  --config /secure/etgb/harness-config.json \
  --output .elmos/etgb/harness-preflight.json
```

`READY_FOR_EXTERNAL_EXECUTION_CONFIG` proves only that the configuration and
public-key inventory are structurally present. Before a full campaign, execute
one authorized canary per adapter and verify authentication, signature,
request binding, evidence digests, cleanup, timeout, retry and revocation paths.

## Phase 4: create the exact 256-shard plan

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . plan --profile release --shards 256 \
  --candidate-digest 'sha256:<candidate-digest>' \
  --output .elmos/etgb/release-plan-v11.json
```

Archive the plan and its digest. All workers must use the same candidate and
plan. Never regenerate a plan during an active campaign.

## Phase 5: execute every shard

Allocate one durable state database and result file per shard. Issue a unique,
monotonically fenced lease to each worker. The checkpoint digest must identify
the exact resume boundary. Example for shard 0:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . run --profile release \
  --plan .elmos/etgb/release-plan-v11.json --shard-id 0 \
  --candidate /secure/etgb/frozen-candidate.json \
  --harness-config /secure/etgb/harness-config.json \
  --tenant-id '<tenant>' --project-id '<project>' \
  --task-id '<campaign>' --environment-id '<production-equivalent-environment>' \
  --authority-id '<approved-authority>' --owner '<worker-identity>' \
  --fencing-token '<lease-epoch>' \
  --checkpoint-digest 'sha256:<checkpoint-digest>' \
  --state-db .elmos/etgb/state/shard-000.sqlite \
  --artifact-root .elmos/etgb/evidence/release/shard-000 \
  --license-reviews /secure/etgb/license-reviews.jsonl \
  --trust-store /secure/etgb/release-public-trust-store.json \
  --output .elmos/etgb/results/shard-000.jsonl
```

Repeat for shard IDs 0 through 255 through an approved scheduler. A scheduler
must preserve idempotency keys, fencing, bounded retries, cancellation,
checkpoint resume, fair resource limits and tenant isolation. It may not mark
`failed`, `error`, `unavailable`, `skipped`, unsigned, duplicate, stale,
or unbound results as passed.

## Phase 6: merge and verify the complete result set

Invoke `merge-results` with all 256 `--result` files, the same plan and
candidate digest, and the worker public-key trust store. This shell fragment
constructs the repeated arguments without relying on a glob:

```bash
result_args=()
for shard_id in $(seq 0 255); do
  result_path=$(printf '.elmos/etgb/results/shard-%03d.jsonl' "$shard_id")
  test -f "$result_path" || {
    echo "missing shard result: $result_path" >&2
    exit 1
  }
  result_args+=(--result "$result_path")
done

PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . merge-results \
  --plan .elmos/etgb/release-plan-v11.json \
  --candidate-digest 'sha256:<candidate-digest>' \
  --trust-store /secure/etgb/harness-public-trust-store.json \
  "${result_args[@]}" \
  --output .elmos/etgb/release-results.jsonl \
  --receipt .elmos/etgb/release-merge-receipt.json
```

The merge must report exactly 46,664 case identities and 131,452 unique
`(case_id, seed)` records with no omissions or duplicates. It revalidates case
digests, candidate/plan bindings and every external signature.

## Phase 7: request independent verification

Generate an unsigned request only after candidate, corpus, result, coverage,
validation and evidence prerequisites pass:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . attestation-request .elmos/etgb/release-results.jsonl \
  --profile release --candidate-digest 'sha256:<candidate-digest>' \
  --plan .elmos/etgb/release-plan-v11.json \
  --trust-store /secure/etgb/release-public-trust-store.json \
  --license-reviews /secure/etgb/license-reviews.jsonl \
  --output .elmos/etgb/independent-attestation-request.json
```

A separate verifier replays the required evidence, confirms executor/verifier
separation, and signs the exact six-digest subject. The expected structure is
shown in
[`external-qualification/independent-attestation.template.json`](external-qualification/independent-attestation.template.json).
The repository never loads the verifier's private key.

## Phase 8: run the repository release gate

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . gate .elmos/etgb/release-results.jsonl \
  --profile release \
  --plan .elmos/etgb/release-plan-v11.json \
  --candidate-digest 'sha256:<candidate-digest>' \
  --attestation /secure/etgb/independent-attestation.json \
  --trust-store /secure/etgb/release-public-trust-store.json \
  --license-reviews /secure/etgb/license-reviews.jsonl \
  --independent-verifier '<verifier-id>' \
  --output .elmos/etgb/release-gate-v11.json
```

The expected successful code-gate state is
`PROMOTE / EXTERNAL_ATTESTED_NOT_A_PRODUCTION_RELEASE`. Any missing, unknown,
expired, revoked, stale, tampered, self-verified or mismatched input remains
blocked.

## Phase 9: external production certification

Submit the immutable candidate, full plan, merge receipt, release results,
evidence manifests, 17 legal records, role/authorization records, independent
attestation, production-equivalent environment evidence, security review,
cleanup/rollback evidence and residual-risk register to the organization's
certification authority.

The external authority owns its certificate format, validity window, scope,
revocation and renewal. Record its decision separately. Do not patch
`NOT_CERTIFIED` or set a local boolean to simulate this step.

## Recovery and rerun rules

- Preserve the same idempotency key for a transport retry of the same request.
- Increase fencing epochs when reassigning a shard; stale workers must fail.
- Resume only from a verified checkpoint bound to the same candidate and plan.
- Revoke a compromised key before accepting any further record from it.
- Quarantine signature, digest, binding, critical-oracle and policy failures;
  do not retry them as transient transport errors.
- A changed corpus commit, candidate input, plan, oracle, normalization,
  toolchain, authorization, or trust root invalidates affected evidence.
- Keep raw provider evidence and normalized evidence separately.

## Completion checklist

- [ ] Frozen candidate validates and is content-addressed.
- [ ] Seven Harness configurations and canaries pass.
- [ ] 17 of 17 corpus reviews are independently signed and verified.
- [ ] 256 shards complete under valid leases and authority.
- [ ] 46,664 cases and 131,452 case-runs merge exactly once.
- [ ] All critical oracles and non-waivable gates pass.
- [ ] Evidence manifests, byte counts, digests and signatures verify.
- [ ] Executor, verifier, reviewers and approvers satisfy separation rules.
- [ ] Production environment, cleanup, rollback and residual risk are approved.
- [ ] Independent attestation verifies against an active trust root.
- [ ] Repository gate reaches `PROMOTE`.
- [ ] External certification authority issues a scoped decision.
