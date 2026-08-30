# ELMOS Component Dialect Engine

Translates UI components between front-end frameworks — React, TypeScript,
Vue 3, Vue 2, Angular, Svelte, React Native, WeChat Mini Program,
HarmonyOS ArkUI, and Flutter — under a fixed, precisely bounded profile
called `certified-component-v1`, and assembles the results into a target
project that actually builds.

## What is and is not being claimed

Repository-scale, fully-runnable, semantics-preserving conversion between
nine frameworks across three languages (TS/JS, ArkTS, Dart) is not a
solved problem. Nobody has solved it. A tool that claims it is either
lying or silently emitting wrong code wherever its coverage runs out —
and wrong code that compiles is far more dangerous than an honest refusal,
because the app *looks* migrated.

So this engine draws the line explicitly:

- **Inside `certified-component-v1`**, translation is real: a real parser
  builds a canonical model, a hand-written per-framework emitter renders
  it, the target framework's **real compiler** re-validates the output,
  and where both sides can run, both components are **actually rendered**
  and their DOM compared.
- **Outside it**, nothing is guessed. The component is reported `BLOCKED`
  with a machine-readable reason code, and the generated project gets a
  placeholder that **throws loudly** when rendered.
- **The generated project still builds and starts.** That is the honest
  reading of "完整能运行": you get a working project plus an exact
  inventory of what is real and what you must port by hand — never a
  project that quietly does the wrong thing.

`coverage-report.json` records every file. A run with any blocked
component is `PARTIAL`, never rounded up to `COMPLETE` — the same rule
`engines/polyglot-route-engine` already follows.

## Capability matrix (verified, not assumed)

| Framework | Real parser (as source) | Emitter (as target) | Syntax check by real compiler | Real execution comparison |
|---|---|---|---|---|
| React | ✅ TypeScript Compiler API | ✅ | ✅ TypeScript | ✅ `react-dom/server` |
| TypeScript (web) | ✅ TypeScript Compiler API | ✅ | ✅ TypeScript | ✅ `react-dom/server` |
| Vue 3 | ✅ `@vue/compiler-sfc` | ✅ | ✅ `@vue/compiler-sfc` | ✅ `@vue/server-renderer` |
| Vue 2 | ✅ `vue-template-compiler` | ✅ | ✅ `vue-template-compiler` | ✅ `vue-server-renderer` |
| Svelte | ✅ `svelte/compiler` | ✅ | ✅ `svelte/compiler` | ✅ `svelte/server` |
| Angular | ✅ `@angular/compiler` + TS API | ✅ | ✅ `@angular/compiler` | ❌ needs a platform-server bootstrap |
| WeChat Mini Program | ✅ `@wxml/parser` + TS API | ✅ | ✅ `@wxml/parser` + TypeScript | ❌ needs WeChat DevTools |
| React Native | ✅ TypeScript Compiler API | ✅ | ✅ TypeScript | ❌ needs Metro + a simulator |
| HarmonyOS ArkUI | ❌ **emit-only** | ✅ | ❌ no ArkTS compiler available | ❌ needs DevEco Studio |
| Flutter | ❌ **emit-only** | ✅ | ❌ external Flutter/Dart analysis required | ❌ needs a real Flutter device/runtime |

**All 54 direction pairs** (6 real source frameworks x 10 targets, minus
self-pairs) are exercised by tests that run the target's own real compiler.
Where both sides have a real server renderer, the components are actually
rendered and their DOM compared — 20 of the 54 pairs get that stronger
behavioral proof.

Round trips through each real parser are asserted **equal to the canonical
model**, not merely similar: React → Vue 3 → canonical, React → Svelte →
canonical, and React → Angular → canonical are exact; Vue 2 and WeChat
differ only in what those formats genuinely cannot represent (below).

**Why ArkUI and Flutter are emit-only.** ArkTS's `struct` declaration is
not valid TypeScript and has no published standalone parser; Dart requires
the external Dart toolchain owns Flutter source parsing. Rather than ship a
regex "parser" whose output nobody can verify, this engine refuses those two
as sources and says so. The same
call `engines/sql-dialect-engine` makes for Oracle/SQL Server execution
validation.

`PARSEABLE_FRAMEWORKS` is a promise the tests enforce: a test drives a real
component through every framework the registry declares parseable, so the
registry cannot advertise a capability the engine lacks.

## certified-component-v1 scope

Each component is read independently: a named function component with an inline
destructured props object, `useState` state, and a single root element. Several
components may share one source file; helpers that return no JSX are excluded
explicitly rather than counted as failed components.

- **Prop types:** `string`, `number`, `boolean`; optional props with
  literal defaults; bounded structural object/array shapes; `on*`-named
  callback props taking at most one primitive argument; and **list props**
  typed `T[]` where `T` is a primitive or a bounded object shape. Nested
  object paths are supported, while object/array values still cannot be
  rendered as scalars. The props object may be annotated inline, by a
  same-file type/interface, or by an exact type resolved through the project
  checker.
- **State:** `useState` with a literal or recursively closed object/array
  initializer (including an exact immutable module constant); structured
  state must have a checker-proven shape. Vue uses `ref()`.
- **Expressions:** identifiers, literals, `! && || + - * / %`, comparisons,
  and ternaries, plus bounded pure numeric functions `Math.min`/`Math.max`
  (1–8 numeric arguments), `Math.floor`, `Math.ceil`, `Math.abs`, and
  `Math.round`; bounded string methods; literal-bound `slice`; explicit
  `toLocaleString("zh-CN"|"en-US")`; typed object lookup; CSS Module
  tokens; and stateless regular-expression predicates. Static and derived
  collections support constrained `map`, `filter`, `reduce`,
  `Math.max(...map(...))` and `join`. Global/sticky regexes, arbitrary calls,
  and unknown structures remain blocked.
- **Event handlers:** a flat list of state assignments and callback
  invocations, including the typed input-event value for `onChange`/`onInput`.
  No loops, conditionals, `async`, or arbitrary calls.
- **Elements:** `div span p button input label a h1–h6 ul ol li strong em i br
  small code dl dt dd` plus the semantic containers `section article header
  footer nav main aside`. Still refused, because there is no honest equivalent on
  React Native / ArkUI / Flutter: `table` and friends (no table model —
  faking one changes column sizing, spanning and accessibility), `form`
  (no submit event on RN, so `onSubmit` would be silently dropped), and
  `img`/`video` (need asset resolution, which is a feature not a tag).
- **Attributes:** `class id href type placeholder value disabled name for
  checked maxLength role aria-* data-* tabIndex style`, static or bound to a
  certified expression. A default
  import from `*.module.css` may provide a static class token such as
  `styles.empty`; the token is preserved, but the source stylesheet is not
  copied or certified by this engine.
- **Events:** `onClick onChange onInput onSubmit`.
- **Structure:** nested elements, text, interpolation, a single flat
  conditional (ternary / `v-if`+`v-else` / `wx:if`+`wx:else`), and
  **list rendering** (`.map` / `v-for` / `{#each}` / `*ngFor` / `wx:for` /
  `ForEach` / Dart `.map`), including only type-checked static and derived
  sources with stable object keys.
- **Composition:** a component may render **another certified component**
  — `<Child label={title} />`. Props only: no children/slot projection
  (each target evaluates it differently) and no event bindings on the
  child. Recursion is refused.
- **Several components per file** are read independently, so one
  component outside the subset costs exactly itself rather than blanking
  out the ones declared beside it. Functions that return no JSX are
  helpers, not components: nothing is emitted for them and they are
  listed under `helpersNotMigrated` so the omission is explicit.
- **List rendering** iterates a declared list prop, immutable static collection,
  or a bounded `map`/`filter` derivation with a plain item binding and exactly
  one body element. Object elements need an identity field (`id`, or exactly
  one field ending in `Id`/`Key`) because every target needs a stable list
  key. No index binding, nested lists, async collections, or untyped
  derivations.

Everything else — effects and other hooks,
slots/children, refs, context, routing, styling systems, async data —
raises `DialectError` and is reported `BLOCKED`.

## Cross-platform IR, target adapters and hand-port ownership

Every successfully parsed component is lowered to the typed
`elmos.cross-platform-component-ir`. It keeps render nodes, state transitions,
effect obligations, data shapes, derived collections, slots, platform
semantics, styling, accessibility and every target adapter plan in one
digest-bound record. `target-adapters.ts` is the only target dispatch surface;
the existing framework emitters are invoked behind their named adapter, so a
target cannot be treated as complete merely because it can print source text.

Source constructs that the canonical parser cannot represent do not receive a
fabricated IR. `scan` emits a `manualPortPlan` with the semantic category,
reason code and required evidence. Once a human has implemented the target,
`handoff mark-ported` records `ownership: "HAND_PORTED"`; later repository
runs preserve that file and report stale source changes instead of overwriting
the work. A hand port is delivery progress, not automatic engine evidence.

The translation report carries an evidence ledger for the exact source/target
tuple. It starts `NOT_RUN` and `NOT_CERTIFIED`. Real runners can bind artifact
bytes with the `evidence bind` command; the ledger computes the digest itself,
requires an executor, and requires a distinct verifier for independent review.
It never promotes a release or certification claim. `sourceTrace` currently
declares `COMPONENT_MODEL_ONLY` with a null source range because the canonical
parser has not yet materialized exact AST spans.

```bash
node dist/cli.js evidence init \
  --source-file ./Counter.tsx --source-framework react \
  --target-framework vue3 --output ./evidence/counter
node dist/cli.js evidence validate --file ./evidence/counter/evidence-ledger.json
node dist/cli.js evidence bind \
  --file ./evidence/counter/evidence-ledger.json --record-id browser \
  --status PASSED --artifact-file ./browser-result.json --executor playwright-runner
```

The command records evidence produced elsewhere; it does not turn a local
browser run into device, platform, independent or production certification.

## Defects this engine exists to prevent

All four of these compile perfectly cleanly on the target and go wrong
only at runtime. Each was found by running the real toolchain, and each is
locked down by a test:

1. **Vue: `count.value = ...` inside a template.** `@vue/compiler-sfc`
   accepts it silently, but template refs are auto-unwrapped, so the
   assignment lands on a primitive and state never changes. Handler bodies
   are therefore rendered with template scoping.
2. **WeChat: `setData` breaks React's closure semantics.** In React,
   `setCount(count + step); onDone(count)` passes the **old** `count`.
   WeChat updates `this.data` **synchronously**, so a direct
   transliteration passes the **new** one. The emitter snapshots read state
   at handler entry (`const count$0 = this.data.count;`).
3. **React Native: bare text crashes on device.**
   `<Pressable>add</Pressable>` type-checks and then throws *"Text strings
   must be rendered within a `<Text>` component"* at runtime. Text under a
   non-`Text` container is wrapped automatically.
4. **Vue vs React whitespace.** Vue preserves the indentation whitespace
   around text; React strips it, so pretty-printing alone changes
   `<strong>small</strong>` into `<strong> small </strong>`. Caught by the
   SSR comparison, fixed by inlining text-only children.
5. **Vue 2 hides `class` from `attrsList`.** `vue-template-compiler`
   hoists `class`/`:class` into dedicated `staticClass`/`classBinding`
   fields, so a parser reading only `attrsList` drops every class
   attribute silently. Caught by the round-trip equality assertion.

## Known, documented information loss

Not every framework can represent everything the canonical model holds.
Where that happens the loss is reported as a translation note, never
papered over:

- **Vue 2 cannot type an emit payload.** The Options API has no
  `defineEmits<...>()`, so `onDone: (value: number) => void` survives a
  round trip only as `onDone: () => void`. `paramType` is left undefined
  rather than inferred from the call site, because a guess would be
  emitted as fact by the next translation.
- **React Native has no CSS.** A `class="counter"` becomes an empty
  `StyleSheet` entry and a note saying styling was not translated.
- **Vue 2 and WeChat cannot describe a list element.** Their runtime prop
  declarations say only `Array`, with no element shape. Reconstructing it
  from template usage would mean guessing at field *types*, so both fail
  closed as list *sources* (`CERTIFIED_COMPONENT_UNRECOVERABLE_LIST_ELEMENT`)
  while remaining fully supported list *targets*. React, Vue 3, Svelte and
  Angular all carry the element type and round-trip lists exactly.
- **WeChat cannot express a required prop.** A `properties` entry always
  carries a default value, so a required prop is emitted with a synthesized
  default and reads back as optional. Its `triggerEvent` detail is untyped,
  so callback payload types are lost the same way Vue 2 loses them.
- **The WeChat mini program has no HTML.** Tags are mapped to built-in
  components and semantic tags (`h1`–`h6`, `strong`, `em`) get generated
  WXSS classes; the source project's own CSS is not translated.

## Local run

```bash
npm ci
npm run build
npm test
```

`npm ci` rather than `npm install`: `package-lock.json` is committed, and
the exact toolchain versions are part of the contract. This engine's
behavior depends on specific compiler internals — `vue-template-compiler`
hoisting `class` out of `attrsList`, Svelte's TypeScript AST naming a
parameter list `parameters`, Angular's `*ngIf` else branch living in a
sibling `<ng-template>` — so a resolver that quietly picked a different
minor version could change results without changing a line of source.

The default suite runs the real toolchains and the real SSR comparison.
The end-to-end build test is opt-in because it needs network access and
several minutes:

```bash
ELMOS_CDE_VERIFY_BUILD=1 npm test
```

## Find out the coverage BEFORE migrating

A certified subset is only honest if its boundary is visible in advance.
`scan` answers "how much of this repository can actually be converted?"
without writing anything or even picking a target framework:

```bash
node dist/cli.js scan \
  --repository ./my-react-app \
  --source-framework react \
  --output ./feasibility
```

It parses every discovered component with its framework's **real
compiler**, then reports:

- how many are inside `certified-component-v1`, as an exact count;
- what is blocking the rest, **ranked by frequency**, with a
  plain-language explanation and example files for each reason code;
- the same rolled up by family (props/types, state, structure,
  expressions, handlers, list rendering, elements/attributes).

Both `feasibility-report.json` and `feasibility-report.md` are written,
because the migration decision gets made by someone who will not read
JSON — and if the honest version is only machine-readable, the optimistic
version is what reaches the decision.

Three properties make the number trustworthy:

- **It is an upper bound, and the report says so.** Parsing proves subset
  membership from the *source* side; each emission is still re-validated
  by the target's real compiler during a real run, where a component can
  still be blocked. `repository` produces the verified number.
- **The denominator is not shrunk.** Files that turn out not to be
  components (helpers, hooks, barrel re-exports) stay in the count under
  `CERTIFIED_COMPONENT_EXPECTED_ONE_FUNCTION` rather than being quietly
  dropped to flatter the ratio.
- **Engine defects cannot hide inside it.** Anything that is not a
  `DialectError` is counted as `SCAN_ERROR` and reported separately, so a
  crash can never be laundered into "out of subset".

Nothing is sampled or extrapolated; every number is a count of files
really parsed.

### What it says about real code

At the latest local run against this monorepo's `apps/web-console` — a genuine
Next.js application nobody shaped for the subset — the scan reports **28 of 65
components in subset (43.1%)**, **37 explicitly blocked**, and **0 scan errors**.
The ratio is a live upper-bound measurement, not runtime, production, or
certification evidence.

The first run of this scan reported **0 of 28**, and reading it is what
produced every subset expansion since. It showed that
`UNSUPPORTED_TAG` was mostly *not* about HTML tags — 8 of 9 were
component references like `<TranslationStudio />` — and that 11 files
were blocked purely for declaring more than one component. Neither had
anything to do with the subset's semantic limits; both were gaps in the
canonical model. Composition, multi-component files, semantic containers
and same-file props types followed directly, and the measured number is
what moved.

The remaining blockers are honest ones: external/effect hooks and async state,
unknown or union-shaped data, complex `Map`/`Set` derivations, and platform
semantics such as slots, tables, disclosure elements, SVG and document roots.
Those require new typed cross-platform IR and target validation; weakening the
blocker rule would only hide semantic loss.

The dogfood scan runs in the test suite and asserts zero engine errors on
that real code — but deliberately does **not** assert the coverage
number, which would turn an honest measurement into a target to game.

## CLI

Check feasibility before committing to anything:

```bash
node dist/cli.js scan \
  --repository ./my-react-app \
  --source-framework react \
  --output ./feasibility
```

Translate one component, with full evidence:

```bash
node dist/cli.js translate \
  --source-file src/components/Counter.tsx \
  --source-framework react \
  --target-framework vue3 \
  --output out/
```

Translate a whole repository into a buildable project:

```bash
node dist/cli.js repository \
  --repository ./my-react-app \
  --source-framework react \
  --target-framework vue3 \
  --destination ./my-vue-app \
  --verify
```

`--verify` runs the generated project's real build (`npm install` +
`vite build`) and writes `build-verification.json`. For targets whose
toolchain is not obtainable from npm — React Native, WeChat, ArkUI,
Flutter, Angular — it reports `NOT_VERIFIABLE_HERE` and names the exact
missing dependency instead of implying a pass.

Exit codes: `0` only when everything converted (and the build passed if
`--verify` was given); `2` for `PARTIAL`, `BLOCKED`, or a failed build.

## Taking blocked components over by hand

A fail-closed engine with a narrow subset hands you a pile of BLOCKED
components and placeholders that throw. That is honest, but on its own it
is a dead end — the migration stops at the subset boundary. `handoff` is
the other half: your team takes those components over and keeps going,
without the tool fighting them.

```bash
# who owns it
node dist/cli.js handoff assign \
  --destination ./my-vue-app --source-path src/components/Chart.tsx \
  --assignee dana --note "needs the real chart library"

# ...they write src/components/Chart.vue by hand, then:
node dist/cli.js handoff mark-ported \
  --destination ./my-vue-app --repository ./my-react-app \
  --source-path src/components/Chart.tsx --target-path src/components/Chart.vue

node dist/cli.js handoff status --destination ./my-vue-app
```

`handoff.json` lives in the destination project, so the migration state
diffs in review and needs no server.

Three guarantees make this safe to rely on:

- **A re-run never overwrites hand-written code.** Marked components are
  skipped on write. Someone re-running the pipeline next week cannot
  destroy a week of work. Unmarked files remain the engine's — protection
  is opt-in per component, or re-runs would be useless.
- **A hand port goes stale loudly.** The dangerous case is not
  overwriting, it is the opposite: `Chart.tsx` changes upstream and the
  hand-written `Chart.vue` silently keeps rendering last month's
  behavior. Every mark records the SHA-256 of the source it was ported
  from, so a later run reports `SOURCE_CHANGED_SINCE_PORT` and holds
  delivery `INCOMPLETE` instead of quietly shipping a stale component.
- **Hand work is never counted as engine evidence.** A hand-ported
  component has been through no parser, no target compiler and no SSR
  comparison, so it records no `syntaxStatus` and no `executionStatus`,
  and it can never make a run read `COMPLETE`.

That last point is why `coverage-report.json` carries two statuses:

| Field | Question it answers |
|---|---|
| `status` | Did the **engine** convert and verify everything? `COMPLETE` only for a pure engine run. |
| `deliveryStatus` | Is the **migration** finished? `ENGINE_COMPLETE`, `COMPLETE_WITH_HANDOFF` (nothing unhandled, but parts are hand-written and unverified), or `INCOMPLETE`. |

If the subset later widens to cover something you ported by hand, the run
reports `AUTOMATIC_CONVERSION_NOW_AVAILABLE` and still keeps your version.
Replacing hand-written code with generated code is your decision — the
hand version may exist precisely because the automatic one was not good
enough.

A corrupt `handoff.json` makes the run **fail**, rather than being treated
as empty. Starting fresh would silently un-protect every hand-ported file,
which is the exact data loss this feature exists to prevent.

## Relationship to `engines/frontend-client-engine`

They do different jobs and do not overlap:

- **`frontend-client-engine`** (ADR-0035) does bounded repository
  discovery, UI route/state graph construction, migration risk
  classification, accessibility and visual adjudication, release gating,
  and **scaffold generation** for nine framework profiles. Its own README
  is explicit that static generation is not runtime evidence and that
  source business behavior is never executed.
- **This engine** does the semantic layer that was missing: real
  component-level parse → canonical IR → emit → validate, with real
  execution comparison where possible.

Use `frontend-client-engine` to plan and govern a migration; use this
engine to actually convert the components it identified.

## Status

`certified-component-v1` is `EXPERIMENTAL`. 263 tests pass locally against
the real toolchains — TypeScript, `@vue/compiler-sfc`,
`vue-template-compiler`, `@angular/compiler`, `svelte/compiler`,
`@wxml/parser` — including all 54 direction pairs, plus real SSR rendering
with `react-dom/server`, `@vue/server-renderer`, `vue-server-renderer`, and
`svelte/server`. The generated Vue 3 project has been really built with
`vite build`. Independent and external certification remain `NOT_RUN`,
consistent with how this repository reports certification for its other
engines.

## Environment-dependent breakage this engine guards against

Three of the toolchains ship module formats that work when invoked one way
and fail another, which produces bugs that only appear in some callers:

- **`@angular/compiler` and `svelte/server` are ESM-only.** Node 22 can
  `require()` an ES module, so an in-process `require` looks fine and then
  fails inside a CommonJS test runner — whose VM sandbox also refuses
  dynamic `import()` without `--experimental-vm-modules`. Both are
  therefore driven in short-lived Node subprocesses under native ESM. It
  is the genuine compiler/renderer, not a substitute, and it behaves the
  same regardless of how the caller was started.
- **`vue-template-compiler` and `vue-server-renderer` refuse to load** from
  their package entry point when `vue@3` is installed alongside them (a
  hard version-mismatch guard). Their published `build.js` /
  `build.prod.js` artifacts are the same compilers without that guard and
  are used directly.
- **Both Vue majors are installed at once.** `vue` is Vue 3; the Vue 2
  runtime is aliased as `"vue2": "npm:vue@2.7.16"` because one npm name
  cannot hold two versions. It is a real alias, not a typo.
- **Vue 2.7.16 is end-of-life and has no upstream release fixing
  GHSA-5j4c-8p2g-v4jx or GHSA-g3ch-rx76-35fx.** Every repository-owned Vue 2
  compiler entry point therefore runs behind `src/vue2-security.ts`: inputs
  are capped at 1 MiB, known raw-text/consecutive-`<` ReDoS shapes are rejected
  with linear checks, and compiler-sensitive prototype pollution fails closed.
  These controls reduce retained compatibility risk; they do not make the
  upstream packages patched, certified, or suitable for an unrestricted
  production renderer.

Because every one of these is reached through a runtime `require(...)`
rather than a static import, TypeScript cannot verify them and a package
that is installed locally but missing from `package.json` would pass the
whole suite here and fail on a fresh clone. `tests/declared-dependencies.test.ts`
closes that hole: it reads the specifiers out of the sources, checks each
one is declared, resolves every entry point and alias, and loads the
ESM-only ones under native ESM the same way the engine does.
