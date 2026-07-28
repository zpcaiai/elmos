# elmos-intake

Batch 1 of the faithful-first core-language lowering chain
(`intake` → `modules/semantic` → `modules/uir` → `modules/skeleton` →
`modules/lowering`; see `docs/adr/ADR-0023-faithful-first-core-language-lowering.md`).

`RepositoryIntakeService` performs a read-only repository scan, build-manifest
inspection, and (via the injected `BaselineRunner`) an original-repository
baseline build/test run. It deliberately does not generate any target-language
source.

**Not wired to any product surface.** No class under `apps/` constructs a
`RepositoryIntakeService`; every production call site would need to supply a
real `BaselineRunner`, and today none exists outside test fakes -- every
production-shaped construction site uses `BaselineRunner.disabled(...)`. This
module is real and tested in isolation, but it is not part of the request path
for any of the three shipped business lines. See ADR-0023's second addendum
(2026-07-28) before adding more capability here or assuming this module backs
a live feature.
