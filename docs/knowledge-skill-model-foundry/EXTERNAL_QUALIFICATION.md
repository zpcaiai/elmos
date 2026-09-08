# External qualification intake

The repository can verify a complete Foundry external qualification chain. It
does not issue provider, training, deployment, independent-acceptance, or
certification receipts. Every receipt must come from the authority that
performed or judged the corresponding real operation.

## Inputs

The gate takes two strict UTF-8 JSON files:

1. `elmos.foundry.external-trust-store.v1`, containing a positive
   `trust_epoch` and Ed25519 public keys;
2. `elmos.foundry.external-qualification-bundle.v1`, containing exact request
   and signed receipt pairs for provider execution, training, deployment,
   independent acceptance, and certification.

Trust keys contain exactly `authority_id`, `key_id`, `public_key_base64`,
`roles`, `not_before`, `not_after`, and `revoked`. Supported roles are
`PROVIDER`, `TRAINING_PROVIDER`, `DEPLOYMENT_PROVIDER`,
`INDEPENDENT_VERIFIER`, and `CERTIFICATION_AUTHORITY`. Roles and keys fail
closed when unknown, expired, revoked, duplicated, or ambiguous. Independent
verifier and certification authority identities cannot share another role or
public key.

The bundle contains exactly these fields:

```text
schema_version
provider_request              provider_receipt
training_request              training_receipt
deployment_request            deployment_receipt
acceptance_request            acceptance_receipt
certification_request         certification_receipt
```

`certification_receipt` may be `null`. In that case, verified provider,
training, deployment, and independent acceptance evidence can reach
`VERIFIED_INDEPENDENT`, while certification remains `NOT_CERTIFIED`.

The request and receipt schemas are defined by `ProviderEvidenceRequest`,
`ExternalRunRequest`, `IndependentAcceptanceRequest`, and
`CertificationRequest` in the Foundry engine. The intake rejects extra or
missing request fields, duplicate or case-colliding JSON keys, noncanonical
identifiers and digests, incomplete output sets, skipped or unknown acceptance
cases, stale trust epochs, invalid signature/time intervals, and broken receipt
bindings.

## Chain invariants

The verifier requires:

- one tenant, project, and producer across training, deployment, acceptance,
  and certification requests;
- acceptance and certification to target the verified deployment;
- the actual training and deployment executor identities to match the executor
  set named by acceptance and certification;
- provider, training, and deployment receipt digests to match the maps bound by
  acceptance and certification;
- the independent verifier on the signed acceptance receipt to match the
  verifier named by the certification request;
- training to finish before deployment starts and deployment to finish no later
  than the evaluation time;
- valid Ed25519 signatures from role-authorized public keys; and
- a current, separately authorized certification receipt before returning
  `CERTIFIED`.

## Operation

Keep the evidence bundle, public trust store, and output decision outside the
repository. Run:

```bash
FOUNDRY_EXTERNAL_BUNDLE=/secure/input/foundry-evidence.json \
FOUNDRY_EXTERNAL_TRUST_STORE=/secure/input/foundry-trust.json \
FOUNDRY_EXTERNAL_DECISION=/secure/output/foundry-decision.json \
make knowledge-skill-model-foundry-external-gate
```

The verifier reuses the repository's Ed25519 verification backend and contains
no private key or signing path. The local qualification receipt includes that
shared backend in its implementation-tree digest. The gate writes the decision
atomically with mode `0600` and binds the accepted trust store by digest. Exit
status is `0` only for a verified current certification receipt, `1` for a
rejected or still uncertified chain, and `2` when required gate configuration
is absent.

The default `make knowledge-skill-model-foundry-skills` target remains a local
engineering qualification and never reads external credentials or runs this
external gate.

## Current evidence state

No Foundry external bundle or trust store is configured in this checkout.
Provider execution, real training and deployment, independent acceptance, and
external certification therefore remain `NOT_RUN`; the package remains
`NOT_CERTIFIED`. Test fixtures exercise verification behavior only and are not
qualification evidence.
