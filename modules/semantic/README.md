# elmos-semantic

Batch 2 of the faithful-first core-language lowering chain
(`modules/intake` → `semantic` → `modules/uir` → `modules/skeleton` →
`modules/lowering`; see `docs/adr/ADR-0023-faithful-first-core-language-lowering.md`).

`SemanticAnalysisPipeline` consumes `modules/intake`'s output and produces the
semantic-obligation model that `modules/uir` lifts into UIR declarations.

**Not wired to any product surface.** This module's only caller inside the
repository is `modules/uir`; nothing under `apps/` depends on `elmos-semantic`.
See ADR-0023's second addendum (2026-07-28) before adding more capability here
or assuming this module backs a live feature -- the product's actual shipped
cross-language capability is `engines/polyglot-route-engine`, which does not
use this pipeline.
