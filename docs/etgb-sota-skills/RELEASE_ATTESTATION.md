# ETGB release evidence contract

The local ETGB runtime can produce `READY_FOR_EXTERNAL_GATE`, but it cannot
manufacture an external release decision. A release/golden gate requires all
of the following to be true:

- every locked corpus has an approved, non-expired, Ed25519-signed record in
  `corpora/license-reviews.jsonl`;
- the trust store in `corpora/trust-store.json` contains the non-revoked public
  key used by each review and attestation;
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
  --candidate-digest <candidate-sha256> \
  --attestation <signed-attestation.json> \
  --trust-store <trust-store.json> \
  --independent-verifier <verifier-id>
```

Missing, stale, malformed, self-signed, tampered, or unbound records remain
`BLOCKED`/`NOT_CERTIFIED`. The verifier only checks evidence; it never signs
on behalf of an external owner and never performs deployment or production
canary operations.
