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
verification with a revoked public key is not independent certification.

## Required recovery

1. Ethan generates and retains a replacement private key outside the repository,
   preferably in an HSM/KMS.
2. Ethan authenticates the new public-key fingerprint through an independent
   channel.
3. Release Control adds only that public key and an explicit scoped trust record.
4. Exact-SHA evidence is re-executed in the named real environments with identity,
   authorization, raw logs, environment, workload, timestamps, and replay command.
5. Ethan independently replays and signs the immutable request outside the
   repository. Only the conservative gate may then change the decision.

Until all five steps finish, external execution, customer acceptance,
independent verification, and certification remain `NOT_RUN / NOT_CERTIFIED`.
