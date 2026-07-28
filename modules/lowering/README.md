# elmos-lowering

Batch 5/6 of the faithful-first core-language lowering chain
(`modules/intake` → `modules/semantic` → `modules/uir` → `modules/skeleton` →
`lowering`; see `docs/adr/ADR-0023-faithful-first-core-language-lowering.md`).

`MethodBodyLoweringService` patches one callable at a time into an
already-existing target repository (`patches/`, `mappings/`, `reports/`
evidence files) via injected `TargetEmitter`/`StaticValidator` maps. It never
assembles or build-verifies a complete standalone target-language project.

`PolyglotRouteEngineBridge` (2026-07-28) is a real, tested implementation of
both `TargetEmitter` and `StaticValidator`, delegating via subprocess to
`engines/polyglot-route-engine`'s `emit`/`check` CLI for that engine's
`typed-pure-function-v1` profile. It is real and passes its own test suite,
but:

- it requires `UirModels.Declaration.languageSemantics().get("sourceText")`,
  which nothing in `modules/uir`'s lifter populates today (fails closed with
  `TARGET_EMITTER_SOURCE_TEXT_UNAVAILABLE` otherwise), and
- **nothing under `apps/` constructs a `MethodBodyLoweringService` or wires
  this bridge into a running Spring context.** This module is not on the
  request path for any of the three shipped business lines.

The product's actual, shipped "whole-repository cross-language conversion"
capability (`/translation` in `apps/web-console`, `routes/inventory.json`,
`docs/BUSINESS_LINE_CLOSURE_MATRIX.md`'s "全库跨语言转换 M29" row) is built
entirely on `engines/polyglot-route-engine` + `engines/dotnet-engine` +
`engines/frontend-client-engine` and does not use this module at all. See
ADR-0023's second addendum (2026-07-28) for the full audit trail before
investing further here, or before assuming a gap found in this module implies
a gap in the shipped product.
