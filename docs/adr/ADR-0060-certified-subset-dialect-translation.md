# ADR-0060: Certified-subset dialect translation for SQL and UI components

## Status

Accepted on 2026-07-29. Supersedes nothing; complements ADR-0023
(faithful-first core language lowering) and ADR-0035 (frontend and client
as a fourth execution engine).

## Context

Two translation requests arrived with a stated requirement of "100%
success" — SQL rewriting between mainstream databases, and repository-scale
conversion between front-end frameworks (Vue 2, Vue 3, TypeScript, Angular,
React, React Native, HarmonyOS ArkUI, Flutter, WeChat Mini Program).

Neither can be met as stated. Arbitrary SQL diverges across vendors in
stored procedures, window-function edge cases, locking hints, partitioning
and vendor functions. Arbitrary UI components diverge across three
languages (TS/JS, ArkTS, Dart) in state models, lifecycle, styling systems
and rendering semantics. No tool has solved either problem, and a tool that
claims to has necessarily chosen to emit wrong output wherever its coverage
runs out.

That failure mode is worse than refusal. Output that compiles cleanly and
behaves differently is invisible: the migration *looks* complete. This
repository already rejects that trade elsewhere — `CanonicalDatabaseIr`
carries `DynamicSqlStatus` and `requiresManualRedesign()`, and
`engines/polyglot-route-engine` reports `PARTIAL` rather than rounding an
incomplete run up to `COMPLETE`.

## Decision

Translate only inside an explicitly enumerated **certified subset**, and
fail closed outside it.

- `engines/sql-dialect-engine` implements `certified-ddl-v1`: a single
  `CREATE TABLE` or `CREATE INDEX` across PostgreSQL, MySQL, Oracle and SQL
  Server, with a fixed type, constraint and referential-action allowlist.
- `engines/component-dialect-engine` implements `certified-component-v1`: a
  single function component with primitive props, `useState`-equivalent
  state, a bounded element/attribute/event allowlist and one flat
  conditional, across ten front-end frameworks.

Four rules bind both engines:

1. **Real compiler frontends, never string templates.** Parsing uses each
   ecosystem's own compiler — `sqlglot`; the TypeScript Compiler API,
   `@vue/compiler-sfc`, `vue-template-compiler`, `@angular/compiler`,
   `svelte/compiler`, `@wxml/parser`. Emission is hand-written per vendor
   and per framework, because the differences that matter are exactly the
   ones a shared emitter erases.

2. **The vendor's own compiler re-validates every emission.** A
   canonical-model bug that produces invalid target source is caught, not
   trusted.

3. **Behavioral equivalence is proven by execution wherever a real runtime
   is obtainable.** Postgres/MySQL DDL is executed against a real database
   given a DSN; React, TypeScript, Vue 3, Vue 2 and Svelte components are
   really rendered and their DOM compared. Where the runtime is not
   obtainable (Oracle, SQL Server, Angular, React Native, WeChat, ArkUI,
   Flutter) the report says `EXECUTION_NOT_AVAILABLE` and names the missing
   dependency.

4. **Anything outside the subset raises `DialectError` and is reported
   `BLOCKED` with a machine-readable reason code.** Repository runs with
   any blocked component are `PARTIAL`. The generated project still builds
   and starts, with blocked components replaced by placeholders that throw
   loudly rather than render something plausible.

Frameworks with no obtainable parser are **emit-only** and say so: ArkTS's
`struct` declaration is not valid TypeScript and has no published
standalone parser, and Dart requires the Dart SDK. Shipping a regex
"parser" for either would produce output nobody could verify.

## Consequences

- Coverage is narrow and explicit rather than broad and unreliable.
  `coverage-report.json` states per file what is real and what must be
  ported by hand.
- Information a target format genuinely cannot represent is reported as a
  translation note, not silently widened: Vue 2's Options API has no typed
  emit declaration, and WeChat `properties` has no required-prop concept
  and an untyped `triggerEvent` detail.
- Emitters must encode per-target runtime semantics that no type checker
  enforces. Four such defects were found by running the real toolchains and
  are locked down by tests: `count.value = ...` inside a Vue template
  (accepted by the compiler, silently inert); WeChat's synchronous
  `setData` breaking React's closure semantics; bare text under a
  non-`Text` React Native component (throws on device); and Vue preserving
  template whitespace that React strips.
- Three toolchains ship module formats that work one way and fail another —
  `@angular/compiler` and `svelte/server` are ESM-only, while
  `vue-template-compiler` and `vue-server-renderer` refuse to load beside
  `vue@3`. Both classes are handled explicitly so behavior does not depend
  on how the caller was started.
- Widening either subset requires a verified per-target rule and a test,
  not a config flag.

## Addendum: the first subset widening (list rendering)

List rendering is the first construct admitted to
`certified-component-v1` after the profile was fixed, and it is recorded
here because it is the worked example of the "verified per-target rule and
a test, not a config flag" consequence above.

Widening it cost ten per-target decisions, each of which a config flag
would have gotten wrong:

- Every target needs a **stable list key**, and each spells it differently
  — `key={row.id}`, `:key="row.id"`, `(row.id)`, `wx:key="id"` (a field
  *name*, with `*this` for primitives), an ArkUI key function. WeChat's
  form is the trap: `wx:key="row.id"` compiles and silently disables list
  diffing.
- Angular gets `*ngFor` with **no** `trackBy`, because `trackBy` requires
  a component method and methods are outside the profile. An honest
  omission beats an invented method.
- Object elements must carry an identity field (`id`, or exactly one
  `*Id`/`*Key`). With no identity there is no correct key on any target,
  so the parser fails closed rather than falling back to index — index
  keys are precisely the defect this engine exists to prevent.
- Vue 2 and WeChat can **emit** lists but cannot **parse** them back:
  their runtime prop declarations record only `Array`, with no element
  shape. Recovering it from template usage would mean guessing field
  types, so both raise
  `CERTIFIED_COMPONENT_UNRECOVERABLE_LIST_ELEMENT` as sources while
  remaining fully supported targets. Asymmetric capability is recorded,
  not smoothed over.
- Execution comparison had to generate **real sample rows** (2 in the base
  case, 3 in the variant). Rendering an empty list would have "proved"
  that two frameworks agree on rendering nothing — the emptiest possible
  false pass.

Index bindings, destructured items, block-bodied callbacks, mapping over
an expression, and nested lists are all rejected, each because it changes
list-diffing behavior differently per target. The expansion added 33
tests; the suite went from 139 to 172.

## Addendum: the coverage pre-check

A certified subset is only honest if its boundary is visible **before**
anyone commits to a migration. Without a pre-check, the only way to learn
that a repository is 12% convertible is to run the whole conversion and
read the wreckage in `coverage-report.json` — which is both the most
expensive way to find out and the moment a customer concludes the tool was
oversold.

`scan` therefore answers the coverage question up front. It is parse-only,
writes nothing, and takes no target framework, because subset membership
is a property of the source. Four properties keep the number honest:

- **It is an upper bound and says so in the report body.** Parsing proves
  source-side membership; emission is still re-validated by the target's
  real compiler during a real run. A test asserts the bound actually holds
  against `runRepository`, rather than asserting the wording.
- **The denominator is never shrunk.** Files that turn out not to be
  components stay in the count under
  `CERTIFIED_COMPONENT_EXPECTED_ONE_FUNCTION`. Dropping them would be the
  cheapest way to inflate the ratio, so a test forbids it.
- **Engine defects cannot be laundered into it.** Anything that is not a
  `DialectError` becomes `SCAN_ERROR`, counted and reported separately.
- **Nothing is sampled or extrapolated.** Every number is a count of files
  really parsed by a real compiler.

Run against this monorepo's own `apps/web-console`, the scan reports **0
of 28 components in subset** — blocked mainly by files that are not single
components (39%) and by elements outside the certified tag set (32%).
That measurement is recorded here because it is the honest current worth
of the subset on unprepared production code, and because it sets the
priority for further widening more reliably than intuition would. The
dogfood scan runs in the suite and asserts zero engine errors on that real
code, but deliberately does not assert the coverage number — pinning it
would convert an honest measurement into a target to game.

## Addendum: human handoff

A fail-closed engine with a narrow subset is honest but, on its own, a
dead end: the migration stops at the subset boundary. Handoff is the
decision that the boundary is a place work continues, not a place it ends.

Three invariants make it safe to depend on, each enforced by a test:

1. **A re-run never overwrites hand-written code.** Marked components are
   skipped at write time, not written and then restored. Protection is
   opt-in per component; unmarked files stay the engine's, or re-running
   the pipeline would be pointless.
2. **A hand port goes stale loudly.** The real hazard is not overwriting
   but its opposite — the source moves on and the hand port silently keeps
   rendering old behavior. Each mark records the SHA-256 of the source it
   was derived from, so a later run reports `SOURCE_CHANGED_SINCE_PORT`
   and holds `deliveryStatus` at `INCOMPLETE`.
3. **Human work is never engine evidence.** A hand-ported component has
   passed no parser, no target compiler and no SSR comparison. It records
   no syntax or execution status and cannot make a run read `COMPLETE`.

That third invariant forced the report to carry two statuses, because
"did the engine convert everything" and "is the migration finished" are
different questions and collapsing them would let hand work launder itself
into engine evidence. `status` keeps its original engine-only meaning;
`deliveryStatus` adds `COMPLETE_WITH_HANDOFF`, which explicitly says
nothing is unhandled *and* that parts of it carry no verification.

When the subset widens to cover something already ported by hand, the run
reports `AUTOMATIC_CONVERSION_NOW_AVAILABLE` and keeps the hand version.
Replacing human code with generated code is not a decision this engine
gets to make silently — the hand version may exist precisely because the
generated one was inadequate.

A corrupt manifest fails the run rather than being treated as empty.
Degrading to "no marks" would silently un-protect every hand-ported file,
turning a data-integrity problem into data loss.

## Addendum: the pre-check drove the next four expansions

The first `apps/web-console` scan reported 0 of 28, and reading its
blocker ranking rather than guessing is what set the next round of work.
The ranking said something the intuition had wrong:

- `CERTIFIED_COMPONENT_UNSUPPORTED_TAG` was mostly **not** about HTML
  tags. 8 of 9 were component references — `<TranslationStudio />` — which
  the parser was mistaking for unknown elements. Composition, not tag
  coverage, was the gap.
- 11 of 28 files were blocked purely for declaring more than one
  component, which was never a semantic limit — the canonical model was
  simply built one component at a time.

Four expansions followed, each measured rather than assumed:

1. **Composition.** A component may render another certified component.
   The per-target work is registration, and four targets punish getting it
   wrong *silently*: Angular needs both the class import and an `imports:`
   entry on the standalone component, WeChat needs a `usingComponents`
   map entry keyed by kebab-case tag, and Vue 2's Options API needs an
   explicit `components` map. In every one of those cases the emitted
   template compiles cleanly and renders **nothing**. Angular is also
   addressed by selector (`app-status-chip`), never by class name.
2. **Multi-component files**, with per-component failure isolation, so one
   component using an effect hook no longer blanks out the four beside it.
3. **Semantic containers** (`section`, `article`, `header`, `footer`,
   `nav`, `main`, `aside`, plus `ol`, `small`, `code`) — admitted because
   each is a plain block container with an honest equivalent everywhere.
   `table`, `form` and `img` stayed out for the opposite reason.
4. **Same-file props types.** `function C({ a }: Props)` with `interface
   Props` in the same file is exact to resolve; an *imported* props type
   is still refused, because a single-file parser does not know what that
   name means elsewhere.

Two measurement corrections came out of the same work, and both matter
more than they look:

- The scan and the pipeline now count the same way, through one shared
  parse path. A pre-check that counted differently from the run it
  predicts would be worse than no pre-check.
- Functions returning no JSX are classified as **helpers, not failed
  components**, and excluded from the denominator while still being
  listed. Counting them as failures was wrong in both directions: it
  understated coverage and filled the blocker ranking with reasons no
  widening could ever fix. On the real console this was 50 of 83
  functions — large enough that leaving it wrong would have misdirected
  the roadmap.

Measured result on `apps/web-console`: **0 of 28 → 8 of 33 components
(24.2%)**. The remaining blockers are effect hooks and non-primitive prop
types in roughly equal share — genuine semantic boundaries rather than
oversights, which is the point at which further widening stops being
cheap.

## Addendum: measuring the SQL subset, and what it found

`certified-component-v1` had a measured coverage number; `certified-ddl-v1`
did not, which made it the one part of this work whose real-world value was
unknown. A parse-only `scan` was added for it too, and run against this
monorepo's own 64 migration files.

The scan itself needed two decisions the component version did not:

- **Split with the real parser.** `sqlglot.parse` separates statements, not
  a semicolon split, because a semicolon inside a string literal, a
  `$$`-quoted body or a `BEGIN ... END` block would miscount silently.
- **Everything executable stays in the denominator.** The component scanner
  excludes functions returning no JSX because a helper is not a migration
  unit. There is no SQL equivalent: an `ALTER TABLE`, view or stored
  procedure IS work the customer needs done, so excluding it would flatter
  the ratio by hiding exactly what the engine cannot do.

**First result: 8.0%.** Reading it found a genuine defect rather than a
subset limit. Inline `b_id INTEGER REFERENCES b(id)` was rejected while the
table-level `FOREIGN KEY (b_id) REFERENCES b(id)` was accepted -- the same
constraint written two ways, treated identically by all four dialects.
Producing different canonical models for them was wrong, not conservative,
and the README advertised referential actions as supported. Inline `CHECK`
had the same gap. Both now lift into the same canonical fields, asserted by
tests that compare the two spellings' models directly. **8.0% -> 10.3%.**

**A correction to the measurement method also came out of this**, and it
matters more than the fix. Ranking blockers purely by occurrence count is
misleading on real schemas: a single copy-pasted idiom -- one
`CHECK (h IS NULL OR h ~ '^[0-9a-f]{64}$')` using Postgres' regex operator
-- accounted for 340 of 342 occurrences of its blocker. Ranking by count
alone would have pointed the next expansion at what is really one line of
SQL repeated across a schema. Blockers now report **occurrences and
distinct reasons separately**, and the report tells the reader to use the
second. By that measure `PARSE_FAILED` (12 occurrences, 12 distinct) is a
more genuine signal than `UNSUPPORTED_CHECK` (384 occurrences, 6 distinct).

**The honest conclusion is that this profile's gap is structural, not
incremental.** 470 of 910 blocked statements are not `CREATE TABLE` or
`CREATE INDEX` at all -- 228 triggers, 128 `ALTER TABLE`, 18 schemas, 17
functions. A real database migration is mostly `ALTER` and procedural code,
and `certified-ddl-v1` addresses none of it. Widening within `CREATE TABLE`
cannot fix that; only an `ALTER TABLE` profile would, and that is a
different piece of work with its own per-dialect semantics.

## Addendum: certified-alter-v1

The previous addendum concluded that `certified-ddl-v1`'s gap was
structural -- 128 of the blocked statements were `ALTER TABLE`, which the
profile did not address at all. This is that profile.

Scope came from the corpus, not intuition. Of 635 real ALTER actions: 603
`ADD COLUMN`, 29 `ADD CONSTRAINT`, 2 `RENAME COLUMN`, 1 `DROP CONSTRAINT`.
Those five are the profile.

**The refusal is the interesting part.** `ALTER COLUMN TYPE`,
`SET NOT NULL`, `SET DEFAULT` and `DROP DEFAULT` are excluded because MySQL
(`MODIFY c <TYPE> NOT NULL`) and SQL Server (`ALTER COLUMN c <TYPE> NOT
NULL`) both require the column's **full type restated**, and a single ALTER
statement does not carry it. This engine reads one statement with no
catalog, so emitting those targets would mean inventing a type -- the exact
silent corruption the profile exists to prevent. They occur 0 times in the
corpus, so the refusal costs nothing measurable. This is the cleanest
example yet of the rule that a subset boundary should follow what can be
*proven*, not what can be *parsed*.

**Two per-dialect rules are not enforceable by the validation leg**, and
that is worth recording because it changes what the evidence means:

- Oracle has no `ADD COLUMN` keyword (`ALTER TABLE t ADD (c ...)`).
- SQL Server has no `ALTER TABLE ... RENAME COLUMN`; it needs
  `EXEC sp_rename 't.c', 'new', 'COLUMN'`, a different statement kind.

`sqlglot` parses the *wrong* form for both without complaint. So the
syntax-validation leg -- normally the thing that turns an emission into
evidence -- proves nothing here. The rules live in the emitter and are
pinned by direct assertions instead, the same posture already taken for
sqlglot's AUTO_INCREMENT/IDENTITY generation defect. A permissive parser
being mistaken for a validator is a general hazard in this design, and
these two cases are the concrete instances of it.

Measured effect on the same corpus: **10.3% -> 17.1%**. Coverage across
this whole line of work has moved 8.0% -> 10.3% -> 17.1%, each step chosen
by reading the blocker table rather than by guessing. What remains is
honest: triggers and stored procedures are programs rather than schema, and
the largest remaining blocker is a regex `CHECK` idiom SQL Server cannot
express at all.

## External gates

Independent verification and external certification of both profiles remain
`NOT_RUN`. Local test success — including real execution comparison and a
real `vite build` of a generated project — is engineering evidence, not
customer, production or regulatory acceptance.
