# ADR-0023: Faithful-first core-language lowering

- Status: Accepted
- Date: 2026-07-21

## Context

Batch 3 provides a multi-view UIR and explicit semantic obligations; Batch 4 provides target declarations, generated regions and a buildable target skeleton. Generating compact target-language code directly from source syntax would make cross-language differences in evaluation order, numeric precision, absence, collections, exceptions, async behavior and cleanup difficult to audit.

## Decision

Batch 5 uses two separately evidenced phases. Phase A lowers each eligible callable to an explicit faithful target implementation and requires target parser, symbol and type validation plus UIR semantic checks. Phase B may apply reversible Level 1/2 target idioms only after Phase A passes and must repeat validation.

Every automatic operation is selected from a versioned, tested and idempotent rule registry using a target-version capability matrix. Equal-ranked rule conflicts block. Compiler and AST/CST/LST emitters are injected language backends; the orchestration core does not fall back to raw string generation or claim success when a backend is missing.

Patches are callable-scoped, atomic and reversible. They locate stable Target Declaration IDs inside protected generated-body regions, verify base hashes and never overwrite manual content. Opaque/dynamic/unsupported operations create bounded agent or manual packets with locked signatures, evaluation order and effect contracts. Agent output remains untrusted until it passes the same validation and any required human gate.

Module gates L-A through L-D measure generation, deterministic/agent/manual/opaque populations, static validation, source mapping and semantic fidelity independently. Static readiness is not behavioral equivalence.

## Consequences

- Faithful output can be verbose, but its transformations and failure boundaries are reviewable.
- Native Java, Python, C# and TypeScript/JavaScript compiler/emitter workers are deployment prerequisites for real code generation; their absence blocks affected callables.
- The current reference module provides deterministic planning, rule/capability governance, safe patching, artifacts and gates. It deliberately does not pretend that generic text templates implement production compiler backends.
- Batch 6 may operate only on individually eligible modules and must preserve open obligations and provenance.

## Addendum (2026-07-28): a real, narrow-scope backend for `typed-pure-function-v1`

`modules/lowering`'s `TargetEmitter`/`StaticValidator` had no real implementation anywhere
in the codebase; every prior test constructed an inline fake. `PolyglotRouteEngineBridge`
(`modules/lowering/src/main/java/io/elmos/lowering/PolyglotRouteEngineBridge.java`) is now
a real implementation of both, but it does not add a second translation backend to this
codebase. It delegates, via subprocess, to `engines/polyglot-route-engine` -- the same
compiler-backed engine already locally certified for all 12 directed Java/Python/C#/
TypeScript pairs (`routes/inventory.json`) -- restricted to that engine's own
`typed-pure-function-v1` profile. Anything outside that profile fails closed, consistent
with this ADR's "does not fall back to raw string generation or claim success when a
backend is missing" decision.

Two new decomposed entry points were added to the engine to make this possible without
reinventing anything: `emit_only` (analyze + emit, no compilation, no behavior cases --
`engines/polyglot-route-engine/src/elmos_polyglot_route/single_unit.py`) backs
`TargetEmitter.emit()`, and `check_only` (compile/type-check a single file, no harness, no
execution) backs `StaticValidator.validate()`. This split exists because Lowering's
`StaticValidator` is deliberately static-only and carries no behavior-case corpus anywhere
in its data model, while the engine's own `validate()` requires one and executes the code;
rather than fabricate cases, validation here proves only what a real compiler pass can
prove, and `validate()` reuses Skeleton's already-written target file (read-only) to get a
real, correctly-signed compilation context for the spliced-in body.

**Known gap, not papered over:** `emit()` requires the exact original source text via
`declaration.languageSemantics().get("sourceText")`. Nothing in `modules/uir`'s current
PSP-to-UIR lifter populates that key today, so this bridge will fail closed with
`TARGET_EMITTER_SOURCE_TEXT_UNAVAILABLE` for declarations coming through the production
lifter until that lookup is wired in. Unit tests (`PolyglotRouteEngineBridgeTest`) prove
the delegation itself is real by populating `languageSemantics` directly; wiring a real
source-text supplier through the UIR lifter is separate follow-up work, deliberately not
bundled here to avoid solving two problems (real delegation, and UIR source-text plumbing)
in one change.

## Addendum (2026-07-28, second pass): this whole chain is not wired to any product surface

A follow-up audit (same day, later pass) traced every caller of `modules/intake`,
`modules/semantic`, `modules/uir`, `modules/skeleton` and `modules/lowering` across the
repository. None of the five modules is a Maven dependency of anything under `apps/`
(`grep` across every `pom.xml` and every `apps/**/*.java` import finds zero references),
and no Markdown doc outside this ADR mentions any of their artifact IDs. Concretely:

- No controller in `apps/control-plane`, no worker in `apps/java-engine-worker`, and no
  command in `apps/elmosctl` constructs a `RepositoryIntakeService`, a
  `MethodBodyLoweringService`, or anything else from this chain outside of that module's
  own unit tests.
- The product's actual, shipped "whole-repository cross-language conversion" surface
  (`/translation` in `apps/web-console`, backed by `routes/inventory.json` and
  `engines/polyglot-route-engine` + `engines/dotnet-engine` +
  `engines/frontend-client-engine`) was built independently of this chain and never calls
  into it. `docs/BUSINESS_LINE_CLOSURE_MATRIX.md`'s "全库跨语言转换 M29" row describes that
  engine-based surface exclusively; it does not mention `modules/lowering` because that
  module has no bearing on what ships.
- `modules/intake`'s `BaselineRunner` (a sibling gap surfaced by the same audit: every
  production construction site uses `BaselineRunner.disabled(...)`, never a real sandboxed
  implementation) has the identical property -- nothing under `apps/` ever constructs a
  `RepositoryIntakeService` to invoke it.

This is not a newly introduced defect and nothing above -- including
`PolyglotRouteEngineBridge` -- needed to be reverted; it is a real, tested implementation
of real interfaces, and if this chain is ever wired to a product surface in the future it
is ready to be used as-is (modulo the `sourceText` gap above). But as of this addendum,
building further real capability underneath `modules/lowering` (a general sandboxed
`BaselineRunner`, UIR `sourceText` plumbing, a Lowering-side whole-project assembly step,
or Spring wiring into `MethodBodyLoweringService`) would be investing in a codepath no
caller can reach, and a general arbitrary-repository sandboxed build/test executor in
particular is large, security-sensitive scope that should not be started opportunistically.
Two possible futures for this chain, deliberately left as an open decision rather than
picked here: (a) wire it to a real product surface (which would first require deciding
*why* two independent cross-language architectures exist and which one a given caller
should use), or (b) formally mark it superseded/archived. Each of `modules/intake`,
`modules/semantic`, `modules/uir`, `modules/skeleton` and `modules/lowering` now carries a
`README.md` pointing back to this addendum so this does not need to be rediscovered by
grep again.
