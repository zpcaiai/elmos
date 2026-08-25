# AGENTS.md — ELMOS Cache, Staging, and Recovery Package

## Mission

Implement a production-grade, contract-driven, evidence-backed subsystem in the actual ELMOS repository. Do not substitute design prose for repository changes when implementation is requested.

## Mandatory reading order

1. `README.md`
2. `manifest.json`
3. `docs/source-packages/elmos-build-cache-staging-spec.md`
4. The selected skill and all dependency skills
5. Relevant schemas, SQL, OpenAPI, templates, and acceptance cases

## Execution rules

- Inspect the existing repository before selecting frameworks, files, tables, or module boundaries.
- Preserve existing ELMOS architecture unless the selected skill explicitly requires migration.
- Register every stage in the Stage Contract Registry and capability DAG.
- Never write generated content directly into the source repository or live final output.
- Never treat file existence as completion. Use staged-file states, digests, manifests, and validation levels.
- Keep immutable bytes in CAS and mutable orchestration state in SQLite/PostgreSQL.
- Redis may support leases, hot indexes, and coordination; it is never the only recoverable truth.
- Make every mutating action idempotent or compensatable.
- Recheck lease epoch immediately before sealing, checkpoint commit, cache commit, and publication.
- Exact cache and semantic-similarity reuse are separate. Similarity results are candidate-only until freshly validated.
- Use immutable toolchain, rule-pack, model, and prompt identifiers in ActionKeys.
- Never claim completion using stale, forged, incomplete, or producer-only evidence.
- Preserve all unresolved generated/user conflicts; never apply last-writer-wins silently.
- Keep source, secrets, prompts, and credentials out of ordinary telemetry.

## Required implementation evidence

- Source commit or explicit working-tree diff.
- Exact test commands and complete result counts.
- ActionKey/fingerprint examples and cache miss explanations.
- Artifact, tree, and checkpoint digests.
- At least one successful trace and one controlled crash/recovery trace.
- Performance measurements when cache reuse or staging overhead changes.
- Explicit limitations or blockers.

## Definition of done

Production code, migrations/adapters, automated tests, failure injection, telemetry, documentation, feature flags, rollback, and fresh machine-readable evidence must all exist. Run this package’s `./validate.sh` and the ELMOS repository’s own verification suite.
