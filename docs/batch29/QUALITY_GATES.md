# Batch 29 Route Quality Gates

## Gate R29-A — Manifest and ownership

- route manifest validates
- directed source and target differ
- exact compiler/runtime versions are recorded
- route owner and review date exist
- support matrix exists

## Gate R29-B — Engine contracts

- source adapter emits valid PSP
- PSP/UIR references and source locations are valid
- output is deterministic for identical inputs
- target emitter consumes versioned contracts
- no direct control-plane database coupling

## Gate R29-C — Semantic safety

- critical semantic capabilities have executable evidence
- unsupported semantics are explicit
- unknown types are not collapsed to permissive catch-all types
- no silent semantic drops
- compatibility runtime remains inside budget

## Gate R29-D — Real target execution

- real target compiler/runtime invoked
- representative vertical slice builds
- required tests run
- generated public symbols have source trace
- test-integrity violations are zero

## Gate R29-E — Independent evidence

- holdout corpus is physically separate
- holdout cases were not used to author rules
- at least one representative or real repository case exists
- critical behavior regressions are zero
- unknown critical differences are zero

## Gate R29-F — Security, maintenance, and economics

- added dependencies have license/security evidence
- runtime components have owners and version policy
- cost per verified workload is visible
- expected manual effort is visible
- route has a support/maintenance owner

## Gate R29-G — Layered and formal equivalence evidence

- strict evidence format 2 assigns every referenced byte sequence a unique `artifact_id`, exact role, route-relative path, SHA-256, and byte count
- source IR, target re-lift IR, behavior observations, formal input, SMT input, solver result, environment, and captured engine sources bind to their exact artifact identities
- semantic chunk references use RFC 6901 JSON Pointers; the gate resolves each pointer and recomputes the canonical subtree hash
- `formal-input.json` embeds and byte-binds the source/target analyzer inputs, normalized IR, formal function, analyzer/emitter identity, solver identity, implementation files, assumptions, and unsupported semantics
- SMT and solver-result artifacts both bind the same formal-input digest; the proof bundle closes every corpus run and the replay declares its expected result digest
- replay argv is fail-closed: its execution root, interpreter form, Python script bytes, repository/route binding, and expected result must all resolve; relocated packs use a digest-bound route-local integrity launcher and keep native recompilation explicitly external/`NOT_RUN`
- the proved relation is named precisely as canonical normalized source IR to independently re-lifted target IR; original-source/compiler/runtime soundness remains an explicit assumption or `NOT_RUN`
- `PROVED_UNDER_ASSUMPTIONS` may support a `limited / NOT_CERTIFIED` route only; `AXIOM`, `BOUNDED`, `UNKNOWN`, `TIMEOUT`, `NOT_RUN`, and `COUNTEREXAMPLE` do not pass the formal layer

### Exact-eight specialized additions

- the route directory name, `route_key`, source/target tuple, and specialized
  exact-eight membership must agree; only those eight routes may claim this
  stricter module profile. Other pairs such as Java↔Swift are valid governed
  routes but start in the generic function profile at `NOT_RUN`
- development, holdout, and representative corpora independently cover
  integer, finite binary64 transport (including negative-zero bits), and
  boolean branch/logic respectively
- only `integer`, finite `number`, and `boolean` are declared; string and
  number arithmetic are rejected by executed negative cases
- integer arithmetic proof and runtime evidence is scoped to
  `canonical-finite-no-error-input-domain`; overflow and non-finite cases fail
  before native source execution
- every chunk mapping has concrete source and target UTF-8 byte spans bound to
  exact logical files, digests, byte counts, and bounds; missing spans fail
- each module function independently binds and replays formal-input JSON,
  SMT2, and formal-result JSON; assumptions are non-empty, proof strength is
  `THEOREM_UNDER_ASSUMPTIONS`, and compiler/runtime soundness stays `NOT_RUN`
- a passing specialized route remains `limited / NOT_CERTIFIED`; local zero
  unknowns mean zero only inside the exact finite no-error domain

### Node.js exact-eighteen additions

- JavaScript is an independent `javascript` language identity bound to the
  exact Node.js 26.0.0 / ES2022 / ESM profile; TypeScript-on-Node evidence
  cannot satisfy a JavaScript route
- every JavaScript direction requires exact JSDoc parameter/return types,
  concrete UTF-8 spans, per-function replay, and typed-pure-module evidence
- JavaScript integer evidence is limited to the IEEE-754 safe-integer domain;
  finite-number, boolean, and string contracts retain independent guards, and
  TypeScript↔JavaScript cannot infer an integer contract from `number`
- missing/ambiguous types, coercive equality, non-finite or unsafe values,
  CommonJS, async/event-loop behavior, prototype state, I/O, package lifecycle,
  and native addons fail closed or remain explicitly `NOT_RUN`
- the exact eighteen routes do not change the immutable exact-eight profile;
  local success remains `limited / NOT_CERTIFIED` and Node/compiler/runtime
  semantic soundness remains `NOT_RUN`

## Gate R29-H — Small/medium whole-repository matrix

- the repository capability campaign uses the exact thirteen active languages and all 156 directed routes from `scripts/batch29/route_sets.py`; deprecated JavaScript is absent and each direction remains independent
- every route contains one measured `SMALL` and one measured `MEDIUM` workload, for 312 explicit workload results
- each workload binds a passing source baseline build/test, complete source-unit classification, zero skipped/failed/unsupported/unknown units, complete conversion, and a passing whole-target-repository build/test
- every referenced JSON artifact binds campaign/route/repository/class/stage/role in both its reference and verified bytes; IDs, paths, and hard-linked inodes cannot be reused across subjects
- raw inventory, classification, conversion, test, and target-manifest detail is parsed to recompute all self-reported counts; swaps or counter-only claims fail
- executor and verifier identities differ per run and their role sets remain disjoint across the campaign
- only `scripts/batch29/run_repository_gate.py` may derive repository capability readiness; complete local evidence reaches at most `READY_FOR_EXTERNAL_GATE / NOT_CERTIFIED`
- `make b29-repository-contract-check` validates the checked-in schemas, command, tests, and documentation without manufacturing execution evidence
- `make b29-repository-gate B29_REPOSITORY_CAMPAIGN=<campaign.json>` requires an explicit real current campaign; a missing campaign, `NOT_RUN`, unknown or partial route/class matrix, deprecated JavaScript record, or any zero-tolerance failure exits nonzero and remains `LIMITED / NOT_CERTIFIED`

The detailed contract and bounded repository-size rules are in
`docs/batch29/REPOSITORY_QUALITY_GATES.md`. Former ten-language/90-route
JavaScript evidence is historical-only and cannot satisfy this gate. No
checked-in campaign currently claims that all 156 active routes have passed;
its absence is `NOT_RUN`, not success.

## Certification outcomes

- `certified`: all required gates pass for declared scope
- `limited`: safe, useful subset with explicit conditions
- `experimental`: evidence is promising but not sufficient for customer commitments
- `blocked`: a critical safety or correctness requirement fails
