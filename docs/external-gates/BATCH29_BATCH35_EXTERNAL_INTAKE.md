# Batch 29 and Batch 35 external evidence intake

This intake closes the mechanical handoff between local repository gates and
authorized external evaluation. It does not manufacture external evidence and
does not certify a route or verification pack.

## Boundary

- Local Batch 29 results remain `limited / NOT_CERTIFIED` until the route gate
  evaluates independently produced evidence.
- Local Batch 35 results remain `limited / NOT_CERTIFIED / BLOCKED` until the
  verification gate evaluates an independent holdout and an authorized,
  deidentified, production-derived representative workload.
- A successful intake returns `ACCEPTED_FOR_REPOSITORY_GATE` and always returns
  `certification_decision: NOT_CERTIFIED`.
- The intake never edits `route.json`, `pack.json`, certification files, or
  production systems.
- Intake is a pre-gate integrity check only. The existing Batch 29 and Batch 35
  gates do not consume an intake automatically, do not infer evidence that is
  absent from their own packs, and do not upgrade a route or pack status.

## Required separation

Each passed stage has an Ed25519-signed `external-executor` record and a
separate `independent-verifier` record. Their actors and organizations must be
different, and neither organization may be the subject producer. Batch 35's
representative production workload additionally requires a signed
`customer-workload-authorizer` from a third organization.

Every signed payload binds the intake, Batch, exact subject snapshot digest,
subject key/version, producer actor and organization, stage, and canonical
stage digest. The producer identity is also part of that canonical digest, so
changing either producer field after signing fails closed. The trust store
binds each key to one actor, organization, validity window, and least-privilege
role. Revoked keys and record IDs fail closed.

The subject snapshot is parsed from the same bytes whose size and SHA-256 were
verified. The trust-store schema, identity metadata, key material, and
`TrustStore` decision are likewise derived from one immutable load. Path swaps
or file changes during either load are rejected.

## Workflow

1. The repository owner creates an exact JSON snapshot manifest for the route
   or pack. It must validate against
   `schemas/external-gates/subject-snapshot.schema.json`, bind the subject kind,
   key, version and repository revision, set `file_set_policy` to `exact`, and
   list every in-scope file with its role, SHA-256 and byte count. `--subject-root`
   must name the dedicated directory represented by that manifest. Every entry
   must be a real regular file below that root; missing, changed, extra,
   symlinked, escaping, or non-regular entries are rejected.
   Subject files are SHA-256 streamed twice and are never retained as whole
   byte arrays. Both passes bind device, inode, size, mtime, and ctime. The
   fail-closed limits are 20,000 files, 512 MiB per file, 4 GiB total, 64
   directory levels, and 40,000 scanned entries; the schema publishes the same
   values.
2. Scaffold a `NOT_RUN` handoff:

   ```sh
   python3 scripts/external_gate_intake.py scaffold \
     --batch 29 \
     --intake-id B29-EXTERNAL-001 \
     --subject-key python-to-typescript \
     --subject-version 1.0.0 \
     --subject-snapshot /approved/input/route-snapshot.json \
     --subject-root /approved/input/route-subject \
     --producer-actor elmos-release-owner \
     --producer-organization elmos \
     --output /approved/handoff/intake.json
   ```

3. Authorized external parties execute the untouched corpora/workloads, store
   every required raw artifact under approved evidence roots, fill exact
   digests/byte counts and zero-tolerance metrics, then sign the canonical stage
   binding with their own role keys.
4. The accountable repository gate owner distributes the expected composite
   trust-store digest over an authenticated out-of-band channel. The pin binds
   the trust-store document and every referenced public-key byte snapshot. It
   must not come from the intake, an intake artifact, or the trust-store path
   being validated.
5. Validate without copying private evidence into the repository:

   ```sh
   uv run --with jsonschema python scripts/external_gate_intake.py validate \
     --intake /approved/handoff/intake.json \
     --trust-store /approved/trust/trust-store.json \
     --expected-trust-store-digest sha256:<repository-owner-issued-pin> \
     --evidence-root /approved/handoff \
     --evidence-root /approved/evidence \
     --subject-root /approved/input/route-subject \
     --output /approved/handoff/validated-intake.json
   ```

6. Supply the validated result and original signed intake to the accountable
   repository gate owner. Intake acceptance alone must not change certification
   or replace the Batch 29/35 gate's own evidence bindings.

## Evidence that cannot be created locally

- an independent organization and qualified verifier;
- untouched holdout provenance and proof it was not used for rule authoring;
- authorization to derive and use production workloads;
- deidentification/redaction evidence for production-derived data;
- real external source/target toolchain or runtime observations;
- external approval or certification signatures.

Synthetic keys and fixtures in unit tests prove only that tampering, role
confusion, producer/trusted-actor collisions, actor reuse, missing authorization,
stale or over-broad signature windows, duplicate key IDs, path swaps,
subject-root drift and resource overruns, pin mismatch, and byte drift are rejected. The CI job named
`External intake anti-fabrication (pre-gate only)` runs those mechanics; it is
not independent execution, production workload evidence, or certification.
