# Certification key revocation notice

Effective at `2026-09-13T00:00:00+08:00`, every certification, approval,
verification, customer-acceptance, and reviewer private key that has ever been
committed to this repository is treated as compromised and permanently revoked.

This incident includes:

- `certification/ethan-certifier/certifier-private.pem`;
- all `*.private.pem` files below
  `framework-packs/*/certification/campaign-runs/actor-ethan-certified/keys/`;
- every signature, dossier, receipt, report, external-evidence record, trust
  decision, or `CERTIFIED` claim produced with those keys.

Deletion from the current tree does not remove secrets from Git history. The
old private keys must not be reused, restored, rotated back into service, or
accepted through an alternate trust store. Their public keys remain only for
fingerprint identification and historical byte verification; cryptographic
verification with a revoked public key is not an independent certification.

## Required recovery

1. Ethan generates a new signing key outside the repository, preferably in an
   HSM/KMS. The repository must never receive or be able to read the private key.
2. Ethan authenticates the new public-key fingerprint through a channel
   independent from this repository and its implementers.
3. Release Control adds only the new public key and an explicit, scoped trust
   record. No old signature is grandfathered.
4. Exact-SHA evidence is re-executed in the named real environments. Executor
   and independent verifier identities, authorization, raw logs, environment,
   workload, replay command, timestamps, and completion interval are bound.
5. Ethan independently replays the evidence and signs the immutable request
   outside the repository. Only then may the relevant conservative gate change
   from `BLOCKED / NOT_CERTIFIED`.

Until all five steps finish, external execution, customer acceptance,
independent verification, and certification remain `NOT_RUN / NOT_CERTIFIED`.

Repository enforcement is provided by
`scripts/certification/check_repository_key_hygiene.py` and the
`certification-key-hygiene-check` dependency of `business-line-contracts`.
