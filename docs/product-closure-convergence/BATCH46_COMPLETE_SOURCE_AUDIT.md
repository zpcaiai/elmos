# Product Convergence Complete source audit

## Scope and identity

The supplied `batch46-product-convergence-complete-skills` package is retained
byte-for-byte as a canonical source package. Its 40 source Skills use
package-local numeric IDs `1497` through `1536`.

The package's `Batch 46` label does **not** own the repository's global Batch 46
namespace. Global Batch 46 is already the Project Synthesis PG001 start.
Installing the supplied `b46-*` names directly would create ambiguous routing
and overwrite the established Batch meaning. Runtime ownership therefore stays
under the `conv-*` Product Convergence overlay.

## Verified source facts

- All 180 checksum-owned source files match `CHECKSUMS.sha256`.
- The source contains exactly 40 Skills and 29 JSON Schemas.
- Every source Skill passes the repository's Skill-creator compatibility check.
- All 29 Schemas meta-validate, and the checked-in Reference Product instances
  validate against the source package's bindings.
- The 12 source toolkit tests pass when run with an explicit `jsonschema`
  dependency and unittest discovery.
- The checked-in Reference Product remains `not-run`, incomplete, and rejected
  by both the source gate and the repository gate.

## Source defects isolated by the repository integration

1. **Namespace collision.** All source Skills are named `b46-*`, although global
   Batch 46 already belongs to Project Synthesis.
2. **Registry cycles.** The source registry contains direct cycles
   `1497 <-> 1498` and `1500 <-> 1501`. It also uses range pseudo-identifiers
   `1498-1536` and `1498-1534` instead of exact dependency nodes.
3. **Non-authoritative positive fixture.** The source toolkit's positive gate
   test creates temporary states and evidence locally. It proves that the
   source script can execute; it is not independent customer, production,
   Private Runner, handoff, SLA, unit-economics, or certification evidence.
4. **Dependency declaration gap.** Schema validation requires `jsonschema`, but
   the documented plain `python3` command fails when that dependency is absent.
   The repository target supplies the dependency explicitly.
5. **Interpreter-sensitive test command.** The documented unittest path contains
   a hyphenated directory. The repository uses unittest discovery so it works
   consistently across supported Python runtimes.
6. **Documentation count drift.** The README describes 28 Schemas and 18
   documents, while the immutable source inventory contains 29 Schemas and 19
   files under `docs/batch46-complete`.

The canonical package is not edited to hide these facts. The integration layer
normalizes them and records exact source digests.

## Runtime convergence

The 40 source Skills resolve through an exact source map:

- 30 Skills reuse an existing `conv-*` semantic owner.
- 10 previously missing concerns receive new `conv-*` owners.
- Two source Skills intentionally resolve to the existing edition and
  commercial-package owner, so the 40 sources map to 39 non-conflicting runtime
  semantic owners.
- No source `b46-*` directory is installed under `.agents/skills`.

The normalized prerequisite graph makes `1497` the entry point, places the
lifecycle model before the workflow runtime, expands the acceptance-review
range to exact IDs, and is validated as a 40-node DAG.

## Evidence and authority boundary

The source validators, templates, source gate, normalized dependency graph,
Skill installation, and local tests are engineering evidence only.

Only
`scripts/product-convergence/run_repository_convergence_gate.py` may prepare a
Product Convergence repository decision, and that decision is capped at
`READY_FOR_EXTERNAL_GATE`. It never certifies production, approves deployment,
or accepts a customer outcome. Missing, synthetic, self-verified, unbound, or
not-run external evidence remains `NOT_RUN` and fails closed.
