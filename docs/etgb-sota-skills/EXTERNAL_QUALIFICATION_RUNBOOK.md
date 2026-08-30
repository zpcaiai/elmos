# ETGB v2 external qualification runbook

This runbook drives the repository-owned caller and evidence gate for
`elmos-etgb-full-product-assurance-skills-package-v2.0.0`. It does not create
provider services, legal approvals, production authority, verifier signatures,
or certification. Those inputs must be supplied by independent owners through
secure files and environment references.

The immutable v2 release scope is 75,419 cases and 206,671 exact
`(case_id, seed)` executions. Twelve cases are local fixtures. The remaining
75,407 cases and 206,659 executions require 32 exact external Harness adapters.
All 17 locked corpora require independently signed license-review records.

## 1. Prepare secure inputs

Mount these as regular files outside the repository. Do not put tokens, client
private keys, or signing private keys in Git or chat.

- frozen candidate input and output;
- Harness configuration and public executor trust store;
- one token environment variable per configured adapter;
- custom CA bundles plus mTLS client certificates and private-key path
  environment variables;
- 17 signed `license-review` records and their public trust store;
- signed `role-assignment` and `production-authorization` records;
- later, the independently signed release attestation.

The public trust store keys must be active, non-revoked, expiring Ed25519 keys
whose `record_types` explicitly authorize only the intended record types.
Templates in this directory contain null or empty placeholders and are
deliberately invalid until independent owners complete and sign them.

## 2. Complete independent corpus review

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . corpus-review-request \
  --output .elmos/etgb-v2/corpus-review-request.json

PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . corpus-review-verify \
  --records /secure/etgb/license-reviews.jsonl \
  --trust-store /secure/etgb/release-public-trust-store.json \
  --output .elmos/etgb-v2/corpus-review-verification.json
```

The second command must report `17 / 17` approved and verified. Repository
owners must not sign on behalf of the independent reviewers.

## 3. Freeze the exact candidate

Populate `candidate-input.template.json` with immutable commits, image digests,
model revisions, prompt/rule/Skill digests, and oracle versions, then run:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . freeze-candidate /secure/etgb/candidate-input.json \
  --output /secure/etgb/frozen-candidate.json
```

Never use `latest`, `main`, `master`, `HEAD`, `stable`, or another mutable alias.

## 4. Run one independently authorized canary per adapter

Create the deterministic 32-case canary plan:

```bash
candidate_digest=$(python3 -c 'import json; print(json.load(open("/secure/etgb/frozen-candidate.json"))["candidate_digest"])')

PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . canary-plan --candidate-digest "$candidate_digest" \
  --shards 1 --output /secure/etgb/canary-plan.json
```

Independent owners must issue role and production-authorization records bound
to this canary plan digest. Verify every prerequisite before making a call:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . campaign-preflight \
  --config /secure/etgb/harness-config.json \
  --candidate /secure/etgb/frozen-candidate.json \
  --plan /secure/etgb/canary-plan.json \
  --role-assignments /secure/etgb/canary-role-assignments.json \
  --production-authority /secure/etgb/canary-production-authority.json \
  --trust-store /secure/etgb/release-public-trust-store.json \
  --license-reviews /secure/etgb/license-reviews.jsonl \
  --tenant-id tenant-a --project-id project-a --task-id etgb-canary-a \
  --environment-id production-shadow-a --authority-id authority-a \
  --owner canary-worker-a \
  --output .elmos/etgb-v2/canary-preflight.json
```

Only `READY_FOR_EXTERNAL_EXECUTION` permits the separately authorized run to
start. It remains `NOT_CERTIFIED`. Execute the canary with the same bindings:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . run --profile release-canary \
  --plan /secure/etgb/canary-plan.json \
  --candidate /secure/etgb/frozen-candidate.json \
  --harness-config /secure/etgb/harness-config.json \
  --role-assignments /secure/etgb/canary-role-assignments.json \
  --production-authority /secure/etgb/canary-production-authority.json \
  --trust-store /secure/etgb/release-public-trust-store.json \
  --license-reviews /secure/etgb/license-reviews.jsonl \
  --tenant-id tenant-a --project-id project-a --task-id etgb-canary-a \
  --environment-id production-shadow-a --authority-id authority-a \
  --owner canary-worker-a --fencing-token 1 \
  --checkpoint-digest sha256:<checkpoint-digest> \
  --state-db .elmos/etgb-v2/state/canary.sqlite \
  --artifact-root .elmos/etgb-v2/evidence/canary \
  --output .elmos/etgb-v2/results/canary.jsonl
```

All 32 canary results must pass their critical oracles and retain signed raw
evidence before the release campaign is authorized.

## 5. Build and preflight the complete release campaign

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . plan --profile release --shards 256 \
  --candidate-digest "$candidate_digest" \
  --output /secure/etgb/release-plan.json
```

The release plan has a different digest from the canary plan. Independent
owners must therefore issue new role and production records bound to the full
release plan. Run `campaign-preflight` again with those release records. A
canary authorization cannot authorize the release campaign.

## 6. Execute and merge all release shards

For each shard ID present in `release-plan.json`, invoke `run --profile release`
with the same candidate, plan, tenant/project/task/environment/authority,
release governance records, public trust store, and licensed corpus evidence.
Use a unique positive fencing token, state database, evidence directory, and
result path per worker. A selected scope must equal exactly one declared shard
or the full plan; ad-hoc subsets are rejected.

After every shard reaches a terminal state, merge all outputs:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . merge-results \
  --plan /secure/etgb/release-plan.json \
  --candidate-digest "$candidate_digest" \
  --trust-store /secure/etgb/harness-public-trust-store.json \
  --result .elmos/etgb-v2/results/shard-000.jsonl \
  --result .elmos/etgb-v2/results/shard-001.jsonl \
  --output .elmos/etgb-v2/release-results.jsonl \
  --receipt .elmos/etgb-v2/release-merge-receipt.json
```

Supply every result file, not only the two placeholders shown. The merger
requires exactly 75,419 cases and 206,671 case-runs, rejects duplicate or
missing seeds, re-verifies all external signatures and campaign bindings, and
will not emit a merged result on failure.

## 7. Independent verification and final code gate

Generate the unsigned request only after the exact merged result exists:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . attestation-request .elmos/etgb-v2/release-results.jsonl \
  --profile release --candidate-digest "$candidate_digest" \
  --plan /secure/etgb/release-plan.json \
  --role-assignments /secure/etgb/release-role-assignments.json \
  --production-authority /secure/etgb/release-production-authority.json \
  --trust-store /secure/etgb/release-public-trust-store.json \
  --license-reviews /secure/etgb/license-reviews.jsonl \
  --output .elmos/etgb-v2/independent-attestation-request.json
```

The independent verifier replays the request, inspects native/raw evidence,
and returns an expiring signed attestation. Then run the final gate with that
attestation, the exact role/authority records, and the verifier identity.

The highest code decision is:

`PROMOTE / EXTERNAL_ATTESTED_NOT_A_PRODUCTION_RELEASE`

It is not production certification. Deployment approval, customer acceptance,
regulatory assessment, and external certification remain decisions and
evidence owned by the applicable external authorities.

## Legacy v1.1

Pass
`--package-root skills/subskills/elmos-etgb-sota-skills-package-v1.1.0`
to use the legacy scope: 46,664 cases, 131,452 case-runs, seven external
adapters, and 17 locked corpora. The same signed governance, exact-plan,
production transport, independent verifier, and non-certification boundaries
apply.
