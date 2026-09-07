# Batch 97–104 repository verification

## Scope and identity

The supplied distribution contains exactly 128 Skills: `B97-S01` through `B104-S16`, 16 Skills per Batch. The source identifiers remain in the package-local `batch-local-product-closure` namespace because this repository does not have a single unambiguous global PG allocation covering the package. `scripts/remap_global_ids.py` therefore emits a non-mutating proposal only; it cannot silently rewrite canonical or installed assets.

The normalized package version is `1.0.1-repository.1`. `NORMALIZATION.json` retains the supplied source-tree digest, the explicit repairs and `external_evidence_status: NOT_RUN`. `docs/batch97-104/installed-manifest.json` binds every source ID/name/digest to its installed `$b97-*` through `$b104-*` name, digest and Codex interface.

## Source audit and repairs

The initial source validator passed its own static checks but could silently skip JSON Schema validation when `jsonschema` was unavailable. The source also contained:

- 32 repeated `evidence_bundle.json` output declarations;
- two blocking dependency cycles caused by forward dependencies at `B101-S16` and `B102-S15`;
- incomplete immutable inventory coverage;
- a compiler that emitted empty inputs, outputs and rollback contracts;
- a certification gate that could accept unbound, fabricated digest strings;
- a global-ID remapper that mutated the canonical distribution without namespace authority;
- no Codex `agents/openai.yaml` interfaces.

Repository normalization removes duplicate outputs, changes `B101-S16` to depend on `B101-S15`, changes `B102-S15` to depend on `B102-S14`, regenerates exact manifests/checksums/interfaces and records every repair. The compiler now emits strict, non-empty, default-deny execution contracts for all 128 Skills. All eight JSON Schemas reject placeholder success shapes, and externally consequential templates are explicitly `not_run`.

## Reproducible checks

Run:

```bash
make batch97-104-skills
```

The target performs the importer parity check, immutable package validation, compilation and Schema validation of all 128 Skills, graph cycle/duplicate/dangling tests, transactional installer backup/recovery tests, unapproved-global-ID non-mutation tests, byte-bound evidence anti-fabrication tests and repository installation parity tests. CI executes the same target.

The expected no-evidence certification check is fail-closed:

```bash
python3 elmos-codex-skills-batch97-104-complete/scripts/run_certification_gate.py \
  --package elmos-codex-skills-batch97-104-complete \
  --scope B104-S16
```

It returns non-zero with `status: not_run`. A structurally complete local candidate must bind every evidence file by path, byte count, SHA-256 and required role, plus authorization, runtime attestation, P0 tests and a distinct verifier. Even then, the maximum local decision is `ready_for_external_gate` with `certified: false`.

## Evidence boundary and remaining gates

These repository checks prove package integrity and executable engineering contracts. They do not prove a deployed capability registry, durable scheduler, hardened Private Runner, successful Java/.NET/Python migration, semantic equivalence, portfolio-scale performance, red-team outcome, disaster recovery, customer acceptance, support readiness or Product Certification. Those items remain `NOT_RUN` until authorized external execution, independent review and trust-store signature verification occur.
