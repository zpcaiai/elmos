# elmos-skeleton

> Superseded for product execution. Retained only as reference architecture and
> isolated regression coverage; see ADR-0023's closure decision.

Batch 4 of the faithful-first core-language lowering chain
(`modules/intake` → `modules/semantic` → `modules/uir` → `skeleton` →
`modules/lowering`; see `docs/adr/ADR-0023-faithful-first-core-language-lowering.md`).

`SkeletonGenerationService` produces a buildable target-language skeleton with
protected `<generated-body id="...">` regions that `modules/lowering` later
patches, and it exercises `BaselineRunner` the same way `modules/intake` does.

**Not wired to any product surface.** Nothing under `apps/` depends on
`elmos-skeleton`. See ADR-0023's second addendum (2026-07-28) before adding
more capability here or assuming this module backs a live feature -- the
product's actual shipped cross-language capability is
`engines/polyglot-route-engine`, which does not use this pipeline (and, for
its supported profile, assembles a whole buildable project directly --
see `elmos-polyglot-route assemble` -- rather than patching an existing one).
