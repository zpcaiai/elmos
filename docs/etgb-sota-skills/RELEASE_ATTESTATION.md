# ETGB release evidence contract

The local ETGB runtime can produce `READY_FOR_EXTERNAL_GATE`, but it cannot
manufacture an external release decision. A release/golden gate requires all
of the following to be true:

- every locked corpus has an approved, non-expired, Ed25519-signed record in an
  externally managed `license-reviews.jsonl` evidence file;
- the supplied trust store contains the non-revoked public key used by each
  review and attestation, and each generic key is purpose-bound through its
  `record_types` list;
- an independent verifier signs an attestation whose subject binds the exact
  candidate, score, validation, coverage, corpus, and evidence-manifest
  digests;
- executor and verifier identities are different and the attestation is still
  within its validity window.

The candidate digest uses the release-candidate form `sha256:<64 lowercase hex>`.
The other attestation subject digests use 64 lowercase hexadecimal characters;
all six subject values must bind the exact gate inputs.

The attestation is supplied to the gate instead of a trusted boolean:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . gate .elmos/etgb/release-results.jsonl \
  --profile release \
  --plan .elmos/etgb/release-plan-v11.json \
  --candidate-digest <candidate-sha256> \
  --attestation <signed-attestation.json> \
  --trust-store <trust-store.json> \
  --license-reviews <license-reviews.jsonl> \
  --independent-verifier <verifier-id>
```

Before asking the independent verifier to sign, generate the unsigned request:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . attestation-request .elmos/etgb/release-results.jsonl \
  --profile release --candidate-digest <candidate-sha256> \
  --plan .elmos/etgb/release-plan-v11.json \
  --trust-store <trust-store.json> \
  --license-reviews <license-reviews.jsonl> \
  --output .elmos/etgb/independent-attestation-request.json
```

This command exits non-zero and marks the request `BLOCKED` while any result,
license review, candidate, coverage, validation, or evidence prerequisite is
missing. It never loads a private key or produces a signature.

Missing, stale, malformed, self-signed, tampered, or unbound records remain
`BLOCKED`/`NOT_CERTIFIED`. The verifier only checks evidence; it never signs
on behalf of an external owner and never performs deployment or production
canary operations.
