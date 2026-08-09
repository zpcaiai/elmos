# Batch 30 external certification intake

These files are fail-closed authoring templates for customer-repository,
customer-holdout, rootless Runner/Transformer/Verifier, and organizationally
independent review evidence. They are not evidence and are deliberately marked
`NOT_RUN`; the validator rejects them until every placeholder is removed and
every record is signed.

The machine-readable shapes are:

- `schemas/batch30/external-certification-intake.schema.json`
- `schemas/batch30/external-evidence-trust-store.schema.json`

The fail-closed decision authority is the executable verifier
`scripts/batch30/validate_external_certification_intake.py`. It reuses the
repository Ed25519 verifier and additionally enforces:

- an explicit approved evidence root, local regular files, no path escape or
  symlink, and exact byte count plus `sha256:<64 lowercase hex>`;
- exact pack/version, source and target tuple, pack manifest, version matrix,
  recipe manifest, target profile, migrated artifact, and execution profile;
- a customer authorization scoped to the exact binding, organizations, six
  required evidence types, and all six evidence-content digests;
- dedicated keys and distinct actor, key, public-key-material, and record
  identities for all seven roles;
- distinct producer, customer, rootless-provider, and independent-review
  organizations. Customer roles belong to the customer organization, rootless
  roles to the rootless-provider organization, and the independent verifier to
  the independent organization;
- Ed25519 signatures from the separate trust store, key and record revocation,
  key and envelope validity windows, non-synthetic PASS outcomes, zero unknowns,
  and zero `NOT_RUN` items.

Run the verifier only after the evidence bytes, trust store, and signatures are
available:

```bash
python3 scripts/batch30/validate_external_certification_intake.py \
  framework-packs/<exact-pack> /approved/intake.json \
  --trust-store /approved/trust/trust-store.json \
  --evidence-root /approved/evidence
```

Success means `READY_FOR_EXTERNAL_GATE_REVIEW` and still returns
`certification_decision=NOT_CERTIFIED`. The command does not edit the framework
pack. The framework certification gate keeps promotion disabled by default;
local or synthetic fixtures cannot unlock it.

Signing uses canonical JSON: UTF-8, object keys sorted, and no insignificant
whitespace. Every envelope payload must contain exactly the fields required by
the validator. Public keys embedded in intake data are ignored; only keys in the
separately supplied trust store are accepted. Do not use caller-selected clocks:
the CLI checks validity against its current UTC time.
