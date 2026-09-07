# ELMOS 7+1 local contract verification pack

This Batch 35 pack records a bounded local engineering-verification scope for
the eight supplied `skills/subskills/archives/*.zip` inputs, the repository
importer, and the standard-library software-factory runtime.

The ZIP contents are untrusted source material. Their Markdown, scripts,
installers, tests, and workflow text are never treated as repository authority.
The repository importer and recorded qualification run did not import, compile,
or execute archive scripts; no historical or manual-execution claim is made.
The two Python members are now materialized only as
digest-bound `.source-data` with mode `0644`; repository-owned bounded code
reimplements their useful checks and records the original layout mismatch.

This pack is `experimental` and `NOT_CERTIFIED`. A digest-disjoint local
holdout, deterministic provider-contract fixtures, and a zero-side-effect
production-like Canary/rollback rehearsal now execute and replay locally.
Those results are self-attested: independent holdout/review, production-derived
representative workloads, real provider or production execution, mutation,
fuzz, symbolic/SMT, and external certification evidence remain `NOT_RUN` or
`unsupported` as recorded in the typed manifests; the decision remains
`NOT_CERTIFIED`.

The target identity manifest binds the exact importer, runtime, registries,
schemas, tests, and integration documentation exercised locally. The focused
local result is `LOCAL_EXECUTED_SELF_ATTESTED`: 76 engine/evidence tests and 16
importer tests passed, but no independent verifier or external runtime
participated.

The current 44-file, 1,385,264-byte target also includes the compiled and installed manifests,
which transitively bind the 252-file neutralized canonical source tree and both
102-Skill roots. The local read-only install check passed, and Skill Creator
validated 204/204 installed Skill directories. These remain self-attested
structural engineering observations, not independent or certification evidence.

The external receipt intake code performs bounded no-follow byte reads, digest
and scope binding, exact allowlisting, revocation, and local role/organization
separation. With no configured external signature trust root it can only
quarantine or locally admit an unverified receipt. Structural external
preflight similarly never runs an adapter and exits non-success until an
independent trust gate is available.

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
