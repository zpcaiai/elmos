# ELMOS 7+1 local contract verification pack

This Batch 35 pack records a bounded local engineering-verification scope for
the eight supplied `skills/subskills/archives/*.zip` inputs, the repository
importer, and the standard-library software-factory runtime.

The ZIP contents are untrusted source material. Their Markdown, scripts,
installers, tests, and workflow text are never treated as repository authority
or executed by this pack. The only locally eligible observations are pinned
archive identity, repository-owned importer validation, deterministic contract
checks, and fail-closed runtime tests.

This pack is `experimental` and `NOT_CERTIFIED`. Mutation, fuzz, symbolic/SMT,
independent review, holdout, representative workload, provider, production,
and external certification execution remain `NOT_RUN` or `unsupported` as
recorded in the typed manifests. Structural validation does not upgrade those
states.

The target identity manifest binds the exact importer, runtime, registries,
schemas, tests, and integration documentation exercised locally. The focused
local result is `LOCAL_EXECUTED_SELF_ATTESTED`: 40 tests passed, but no
independent verifier or external runtime participated.

The current 25-file target also includes the compiled and installed manifests,
which transitively bind the 252-file neutralized canonical source tree and both
102-Skill roots. The local read-only install check passed, and Skill Creator
validated 204/204 installed Skill directories. These remain self-attested
structural engineering observations, not independent or certification evidence.

## Local validation

```sh
/opt/homebrew/bin/uv run --quiet --with jsonschema==4.25.1 python \
  scripts/batch35/validate_verification_pack.py \
  verification-packs/elmos-7plus1-local-contract-v1

/opt/homebrew/bin/uv run --quiet --with jsonschema==4.25.1 python \
  scripts/batch35/run_verification_gate.py \
  verification-packs/elmos-7plus1-local-contract-v1
```

The expected conservative gate decision is `NOT_CERTIFIED`.
