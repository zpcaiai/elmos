# elmos-uir

> Superseded for product execution. Retained only as reference architecture and
> isolated regression coverage; see ADR-0023's closure decision.

Batch 3 of the faithful-first core-language lowering chain
(`modules/intake` → `modules/semantic` → `uir` → `modules/skeleton` →
`modules/lowering`; see `docs/adr/ADR-0023-faithful-first-core-language-lowering.md`).

`PspToUirPipeline` lifts `modules/semantic`'s output into the multi-view
Unified Intermediate Representation (`UirModels.Declaration` and friends) that
`modules/skeleton` and `modules/lowering` consume.

**Not wired to any product surface**, and note in particular:
`UirModels.Declaration.languageSemantics()` is a generic extensibility map
that nothing in this lifter currently populates with the original source text
(`"sourceText"`) -- `modules/lowering`'s `PolyglotRouteEngineBridge.emit()`
depends on that key and fails closed without it. See ADR-0023's second
addendum (2026-07-28) before adding more capability here or assuming this
module backs a live feature -- the product's actual shipped cross-language
capability is `engines/polyglot-route-engine`, which does not use this
pipeline.
