# UIR v1 operating contract

Batch 3 consumes only PSP modules eligible for Batch 3. It produces no target project or target-language source. UIR is a semantic superset with linked UIR-H declarations/types, UIR-S structured operations, and derived UIR-C CFG/SSA/effect views; SSA never replaces object identity or structured generation input.

Use versioned dialects and Operation/Region/Block/Value. Preserve null/None/undefined/optional-wrapper, nominal/structural identity, numeric width/overflow, evaluation order, exceptions/rejections, async/cancellation/schedulers, effects, alias/mutability/ownership, dynamic/reflection, source sugar, and language escape operations. Missing semantics become `opaque` or `unknown` with provenance and obligations, never guessed defaults.

Every pass is deterministic, versioned, idempotence-tested where required, source-mapped, and failure-atomic. Every high-risk difference becomes a queryable obligation with a verification strategy. Artifact JSONL order has no meaning; JSON Schema is authoritative and SQLite is rebuildable.

PSP v1 call sites and control-flow summaries do not constitute a complete executable body. Unless an authority adapter supplies complete executable-operation evidence, retain an opaque body remainder with source references, unknown effects, and a blocking verification obligation. Such a module may reach the skeleton gate but cannot receive an automatic-translation gate merely because all known call sites were lifted.

Per-module gates: UIR-A declaration >=.99, operation >=.97, source maps >=.99, no structural errors; UIR-B type/body >=.90 and no blocking diagnostics; UIR-C type >=.95, effects >=.90, unknown <=.05, opaque <=.03, no unstrategized blocking obligation; UIR-D tightens type/effect/call/dynamic/source-map thresholds. Batch 4 requires UIR-B.
