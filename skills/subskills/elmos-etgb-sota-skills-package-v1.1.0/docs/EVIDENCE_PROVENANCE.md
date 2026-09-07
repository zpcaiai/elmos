# Evidence, provenance and chain of custody

Evidence uses content-addressed SHA-256 blobs and an immutable logical manifest. The ledger stores raw restricted evidence and, where allowed, separately digested redacted derivatives.

## Seal

After all artifacts are present, append the seal event, compute the root digest and sign/attest the manifest. Release certification verifies blobs, sizes, event links, root digest, signature and access/retention metadata.

## Required provenance

Candidate, plan, case, corpus, Environment, authority, workspace, source/target, toolchain image, dependencies, model usage, commands, Oracles, checkpoints, side effects, SBOM, build provenance, costs and gates.

## Privacy

Hidden tests and customer source remain in restricted domains. Reports use first-difference summaries and digests. Secret/PII scans occur before publication; a failed scan quarantines the artifact.

## Reference

Use `etgb/evidence.py`, `schemas/evidence-manifest.schema.json`, `evidence_artifact/evidence_seal` tables and `etgb evidence-verify`.
