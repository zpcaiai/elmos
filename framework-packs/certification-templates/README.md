# Batch 30 external certification intake

These files are fail-closed authoring templates for native source/target build
and runtime execution, behavioral equivalence, security, performance,
operability, SBOM, rollback, explicit customer acceptance, organizationally
independent review, and external certification evidence. They are not evidence and are deliberately marked
`NOT_RUN`; the validator rejects them until every placeholder is removed and
every record is signed by a real authorized subject.

The machine-readable shapes are:

- `schemas/batch30/external-certification-intake.schema.json`
- `schemas/batch30/external-evidence-trust-store.schema.json`
- `schemas/batch30/external-evidence-document.schema.json`
- `schemas/batch30/certification-campaign.schema.json`

The fail-closed decision authority is the executable verifier
`scripts/batch30/validate_external_certification_intake.py`. It reuses the
repository Ed25519 verifier and additionally enforces:

- an explicit approved evidence root, local regular files, no path escape or
  symlink, and exact byte count plus `sha256:<64 lowercase hex>`;
- exact pack/version, source and target tuple, pack manifest, version matrix,
  recipe manifest, target profile, migrated artifact, and execution profile;
- every signed evidence document's exact P0-P11 campaign digest and the six
  policy-bound source/target Java, Maven, and container content identities;
- a customer authorization scoped to the exact binding, five organizations,
  thirteen required evidence types, all thirteen executor principals, and all thirteen
  evidence-content digests;
- dedicated keys and distinct actor, key, public-key-material, and record
  identities for all fourteen roles (authorization plus thirteen evidence roles);
- distinct producer, customer, rootless-provider, independent-review, and
  external-certification organizations. Customer roles belong to the customer
  organization, rootless roles to the rootless-provider organization, the
  independent verifier to the independent organization, and the external
  certifier to the certification organization;
- explicit executor actor and organization identities for every evidence item.
  No authorizer or evidence signer may also be an executor anywhere in the
  intake; the independent-review and external-certification signer
  organizations must not execute any evidence role anywhere in the intake;
- Ed25519 signatures from the separate trust store, key and record revocation,
  key and envelope validity windows, non-synthetic role-specific success
  outcomes, zero unknowns, and zero `NOT_RUN` items. Customer acceptance uses
  exact `ACCEPTED` semantics, and the external certificate uses exact signed
  `CERTIFIED` semantics.

Run the verifier only after the evidence bytes, trust store, and signatures are
available:

```bash
python3 scripts/batch30/validate_external_certification_intake.py \
  framework-packs/<exact-pack> /approved/intake.json \
  --trust-store /approved/trust/trust-store.json \
  --evidence-root /approved/evidence
```

Success at the intake layer means the supplied signatures and content bytes were
authenticated for review. It returns `READY_FOR_EXTERNAL_GATE_REVIEW` and still
returns `certification_decision=NOT_CERTIFIED`. The P0-P11 campaign evaluator
then validates the contents, raw evidence, exact versions, zero-tolerance
metrics, chronology, and certificate scope. Only `run_framework_gate.py` may
return `CERTIFIED`, and it re-verifies the external intake on every certified
gate run. Local or synthetic fixtures cannot unlock it.

Validate a checked-in plan without claiming external execution:

```bash
python3 scripts/batch30/certification_campaign.py \
  framework-packs/<exact-pack> --plan-only
```

After real evidence exists, run the complete non-mutating P0-P11 evaluation:

```bash
python3 scripts/batch30/certification_campaign.py \
  framework-packs/<exact-pack> \
  --intake /approved/intake.json \
  --trust-store /approved/trust/trust-store.json \
  --evidence-root /approved/evidence
```

Preview the exact certification mutations without writing the pack:

```bash
python3 scripts/batch30/promote_framework_certification.py \
  framework-packs/<exact-pack> \
  --external-intake /approved/intake.json \
  --trust-store /approved/trust/trust-store.json \
  --evidence-root /approved/evidence
```

The preview must return `READY_TO_APPLY`. An authorized release operator may
then request the atomic promotion explicitly:

```bash
python3 scripts/batch30/promote_framework_certification.py \
  framework-packs/<exact-pack> \
  --external-intake /approved/intake.json \
  --trust-store /approved/trust/trust-store.json \
  --evidence-root /approved/evidence \
  --apply
```

Promotion takes a pack-scoped exclusive lock, re-evaluates every external byte
inside the lock, writes only the authoritative certification documents using
durable atomic replacement, and immediately runs the conservative Batch 30
gate against the live evidence. Any write or gate failure restores the exact
pre-promotion bytes. Existing symlinks, path escapes, malformed or oversized
documents, stale evidence, and concurrent tampering fail closed.

Signing uses canonical JSON: UTF-8, object keys sorted, and no insignificant
whitespace. Every envelope payload must contain exactly the fields required by
the validator. Public keys embedded in intake data are ignored; only keys in the
separately supplied trust store are accepted. Do not use caller-selected clocks:
the CLI checks validity against its current UTC time.
