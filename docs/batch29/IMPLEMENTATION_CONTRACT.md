# Batch 29 Codex Implementation Contract

## Objective

Implement directed, independently certified programming-language migration routes. A route is not complete when code is merely generated; it is complete only when a representative source workload is parsed, lowered, compiled by the real target toolchain, tested, behavior-checked, and supported by a machine-readable certification record.

## Required engineering behavior

1. Inspect before editing. Reuse existing Batch 20–28 contracts and engines.
2. Implement code and tests, not only plans.
3. Work vertically: one full source-to-target slice before broad syntax coverage.
4. Prefer deterministic transformations. Model-assisted output is candidate code and must pass normal validation.
5. Keep directions separate. `java-to-csharp` and `csharp-to-java` have separate manifests, corpora, economics, and status.
6. Keep core UIR framework-neutral. Framework semantics belong in framework contracts/packs.
7. Preserve unsupported nodes and unknown behavior as obligations; never silently drop them.
8. Keep customer-private source, corpora, and recipes isolated.
9. Record source commit, route/profile versions, toolchain digests, recipe digest, model/prompt versions, tests, and evidence.
10. Update the support matrix only after executable evidence exists.

## Required route statuses

- `research`
- `experimental`
- `limited`
- `certified`
- `deprecated`
- `blocked`

## Required capability statuses

- `certified`
- `supported`
- `conditional`
- `experimental`
- `detected-only`
- `blocked`

## Required route evidence

- source engine output and conformance result
- target compiler/build result
- semantic corpus results
- negative/unsupported corpus results
- holdout results
- representative repository result
- source-map coverage
- behavioral comparison for certified scope
- test-integrity result
- compatibility-runtime manifest and budget
- security/license/SBOM result when a runtime or dependency is added
- route economics
