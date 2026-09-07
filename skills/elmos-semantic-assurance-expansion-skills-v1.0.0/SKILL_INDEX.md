## New Semantic Assurance Skills

### Batch {b} ({batch_counts[b]})
- **ELMOS-POLY-169** `elmos-grammar-spec-ingestor` — Ingest normative grammars, vendor dialect grammars and parser artifacts into a versioned grammar model with provenance and ambiguity records.
- **ELMOS-POLY-170** `elmos-dialect-version-detector` — Infer language dialect, standard edition, compiler mode and vendor extensions per module instead of assuming one repository-wide syntax.
- **ELMOS-POLY-171** `elmos-preprocessor-macro-expansion-modeler` — Model preprocessing, include/copy expansion, macros, conditional compilation and generated-source boundaries while retaining source-to-expanded provenance.
- **ELMOS-POLY-172** `elmos-lexical-layout-fidelity-engine` — Preserve lexical tokens, fixed/free-form layout rules, whitespace-significant syntax, continuation columns and source encodings that carry meaning.
- **ELMOS-POLY-173** `elmos-lossless-cst-builder` — Build a lossless concrete syntax tree that retains every token, trivia item, directive and source span required for safe round-trip transformations.
- **ELMOS-POLY-174** `elmos-native-ast-cross-checker` — Cross-check ELMOS CST/AST extraction against native compiler or language-service frontends to detect parser drift and semantic frontend mismatches.
- **ELMOS-POLY-175** `elmos-parse-error-recovery-validator` — Validate partial and malformed repositories without allowing parser recovery to silently invent executable semantics.
- **ELMOS-POLY-176** `elmos-source-roundtrip-preserver` — Guarantee parse→model→print round trips preserve source meaning and intentionally preserved lexical structure before semantic transformation begins.
- **ELMOS-POLY-177** `elmos-comments-directives-trivia-provenance` — Carry comments, pragmas, directives, suppression annotations and non-code source material through conversion with explicit semantic relevance classification.
- **ELMOS-POLY-178** `elmos-symbol-table-builder` — Construct a cross-language canonical symbol table covering declarations, imports, modules, packages, namespaces and external symbols.
- **ELMOS-POLY-179** `elmos-scope-resolution-engine` — Resolve lexical, dynamic, imported, inherited and host-environment scopes and preserve binding identity through target generation.
- **ELMOS-POLY-180** `elmos-overload-dispatch-resolver` — Model overload resolution, multimethod dispatch, virtual dispatch and target-language call selection rather than translating call syntax literally.
- **ELMOS-POLY-181** `elmos-generic-template-specialization-modeler` — Represent Java/C# generics, C++ templates, Rust generics/traits, Swift protocols and specialization/monomorphization consequences.
- **ELMOS-POLY-182** `elmos-annotation-attribute-reflection-modeler` — Capture metadata-driven behavior including annotations, attributes, decorators, reflection, DI scanning and runtime discovery.
- **ELMOS-POLY-183** `elmos-dynamic-language-shape-inference` — Infer runtime object shapes, duck-typed protocols, monkey patches and dynamic call targets with confidence and observed evidence.
- **ELMOS-POLY-184** `elmos-frontend-consistency-gate` — Block transformation when grammar, CST, native AST, symbol or source-roundtrip evidence disagrees beyond declared tolerances.

### Batch {b} ({batch_counts[b]})
- **ELMOS-POLY-185** `elmos-canonical-type-algebra` — Normalize primitive, nominal, structural, algebraic, callable, reference and opaque types into a target-independent algebra with provenance.
- **ELMOS-POLY-186** `elmos-nominal-structural-subtyping-mapper` — Preserve inheritance, interfaces, protocols, duck typing and structural compatibility across different target type systems.
- **ELMOS-POLY-187** `elmos-nullability-optionality-semantics` — Model null, undefined, optional, nullable reference/value types and null-propagation behavior explicitly.
- **ELMOS-POLY-188** `elmos-numeric-type-range-overflow` — Preserve integer widths, signedness, big integers, decimal types, overflow modes, shifts and conversion behavior.
- **ELMOS-POLY-189** `elmos-string-char-codepoint-semantics` — Model byte strings, UTF encodings, code units, code points, graphemes and string indexing/comparison behavior.
- **ELMOS-POLY-190** `elmos-collection-order-mutability-semantics` — Preserve sequence/set/map ordering, equality, hashing, mutability, aliasing and iteration guarantees.
- **ELMOS-POLY-191** `elmos-enum-variant-sumtype-semantics` — Translate enums, tagged unions, variants, discriminated unions and pattern matching while preserving exhaustiveness and representation.
- **ELMOS-POLY-192** `elmos-generics-variance-erasure-semantics` — Preserve variance, bounds, erasure/reification, wildcards and runtime generic metadata across target systems.
- **ELMOS-POLY-193** `elmos-refinement-range-contract-semantics` — Represent Ada/SPARK subtypes, ranges, invariants, pre/postconditions and other refinement constraints as executable/provable obligations.
- **ELMOS-POLY-194** `elmos-lifetime-ownership-borrow-semantics` — Model ownership, borrowing, lifetimes, aliasing and move/copy semantics for safe translation between managed and native languages.
- **ELMOS-POLY-195** `elmos-exception-effect-type-semantics` — Represent checked/unchecked exceptions, Result/error unions, non-local exits and typed effects as part of callable contracts.
- **ELMOS-POLY-196** `elmos-serialization-schema-type-semantics` — Tie in-memory types to JSON/XML/Protobuf/Avro/DB/wire schemas including defaults, unknown fields and evolution rules.
- **ELMOS-POLY-197** `elmos-public-api-binary-compatibility` — Compare source and target public API surfaces, ABI/binary compatibility where relevant, and consumer-visible type semantics.
- **ELMOS-POLY-198** `elmos-type-semantic-loss-gate` — Aggregate type-system obligations and block routes that narrow domains, erase contracts or alter observable type behavior without an approved adaptation.

### Batch {b} ({batch_counts[b]})
- **ELMOS-POLY-199** `elmos-cfg-equivalence-builder` — Build normalized source/target CFGs and compare branch, loop, early-exit and exceptional control-flow structure.
- **ELMOS-POLY-200** `elmos-ssa-dataflow-lowering` — Lower relevant code into SSA-like dataflow form to expose definitions, uses, phi merges and value transformations across languages.
- **ELMOS-POLY-201** `elmos-program-dependence-graph-analyzer` — Construct control/data dependence graphs for slicing, business-rule extraction and semantic comparison across structurally different implementations.
- **ELMOS-POLY-202** `elmos-alias-points-to-analysis` — Approximate and refine heap aliasing, pointer targets and shared mutable state so transformations do not duplicate or detach state accidentally.
- **ELMOS-POLY-203** `elmos-interprocedural-callgraph-resolver` — Resolve direct, virtual, interface, reflection-assisted and callback call edges with confidence for repository-scale semantic obligations.
- **ELMOS-POLY-204** `elmos-side-effect-footprint-model` — Classify reads/writes to memory, DB, files, network, queues, clocks, environment and external systems per operation.
- **ELMOS-POLY-205** `elmos-exception-unwind-equivalence` — Preserve exception matching, stack unwinding, finally/defer/destructor behavior, retry boundaries and error translation.
- **ELMOS-POLY-206** `elmos-resource-lifetime-finalization` — Preserve RAII, try-with-resources, using/defer, GC finalizers and explicit close semantics with failure-path validation.
- **ELMOS-POLY-207** `elmos-closure-capture-lambda-semantics` — Preserve capture-by-value/reference, receiver capture, mutable closures and escaping lifetime behavior.
- **ELMOS-POLY-208** `elmos-iterator-generator-coroutine-semantics` — Model suspension points, yielded values, cleanup, backpressure and resumption state across generator/coroutine constructs.
- **ELMOS-POLY-209** `elmos-async-await-task-semantics` — Preserve scheduling, cancellation, continuation context, structured concurrency and error propagation across async runtimes.
- **ELMOS-POLY-210** `elmos-reflection-dynamic-dispatch-semantics` — Characterize runtime-discovered members, proxy invocation, dynamic method lookup and reflection-visible metadata behavior.
- **ELMOS-POLY-211** `elmos-metaprogramming-runtime-codegen-semantics` — Model eval, macros, generated bytecode/source, expression trees and metaprogramming boundaries that cannot be assumed statically.
- **ELMOS-POLY-212** `elmos-io-environment-observable-semantics` — Normalize observable console, file, environment, process and network interactions for source-target comparison.
- **ELMOS-POLY-213** `elmos-time-randomness-nondeterminism-semantics` — Identify and control clocks, RNG, UUIDs, hash seeds, scheduler order and other nondeterministic inputs to enable fair differential execution.
- **ELMOS-POLY-214** `elmos-control-data-effect-equivalence-gate` — Require closed obligations for CFG, data dependencies, aliasing, effects, errors, resources, async and nondeterminism before behavioral certification.

### Batch {b} ({batch_counts[b]})
- **ELMOS-POLY-215** `elmos-cross-language-memory-model` — Represent happens-before, visibility, atomicity and data-race legality for Java/.NET/C++/Rust/Swift and other concurrency models.
- **ELMOS-POLY-216** `elmos-pointer-layout-endianness-semantics` — Preserve pointer arithmetic, provenance-sensitive operations, alignment, padding, bitfields and byte order for native/record migrations.
- **ELMOS-POLY-217** `elmos-abi-calling-convention-semantics` — Capture platform ABI, calling convention, register/stack classification, symbol mangling and exception ABI obligations.
- **ELMOS-POLY-218** `elmos-ffi-marshalling-semantics` — Generate and verify foreign-function bridges, marshalling, ownership transfer, callbacks and error boundaries between source and target runtimes.
- **ELMOS-POLY-219** `elmos-object-layout-vtable-semantics` — Model native object layout, inheritance offsets, vtables, RTTI and COM-style interfaces where binary interoperability matters.
- **ELMOS-POLY-220** `elmos-atomic-memory-order-semantics` — Map relaxed/acquire/release/seq-cst atomics and language-specific volatile primitives without strengthening/weakening silently.
- **ELMOS-POLY-221** `elmos-lock-condition-semaphore-semantics` — Preserve mutual exclusion, reentrancy, condition-variable wakeups, fairness assumptions and timeout behavior.
- **ELMOS-POLY-222** `elmos-actor-channel-mailbox-semantics` — Represent actor/channel ordering, buffering, supervision, mailbox behavior and failure propagation for distributed/concurrent conversions.
- **ELMOS-POLY-223** `elmos-thread-scheduler-determinism-lab` — Systematically explore permitted thread schedules, races, deadlocks and starvation-sensitive behavior across source and target runtimes.
- **ELMOS-POLY-224** `elmos-integer-ub-language-lawyer` — Classify integer overflow, shifts, casts, uninitialized values and language-specific undefined/implementation-defined behavior before conversion.
- **ELMOS-POLY-225** `elmos-ieee754-floating-point-semantics` — Preserve NaN, infinities, signed zero, rounding, fused operations, extended precision and tolerance policies.
- **ELMOS-POLY-226** `elmos-decimal-money-arithmetic-semantics` — Preserve decimal scale, rounding, packed/zoned decimal, currency precision and monetary comparison rules.
- **ELMOS-POLY-227** `elmos-datetime-timezone-calendar-semantics` — Preserve instant/local date/time, timezone database, DST ambiguity, calendar rules, epoch ranges and serialization.
- **ELMOS-POLY-228** `elmos-text-encoding-collation-locale-semantics` — Preserve EBCDIC/ASCII/Unicode conversions, locale-sensitive casing, collation, normalization and database/string comparison behavior.
- **ELMOS-POLY-229** `elmos-binary-record-wire-layout-semantics` — Preserve fixed records, copybooks, packed fields, alignment, endian, protocol framing and exact byte-level interchange contracts.
- **ELMOS-POLY-230** `elmos-sql-null-collation-isolation-semantics` — Capture three-valued logic, collation, locking/isolation, identity/sequence and vendor procedural differences during language/data migration.
- **ELMOS-POLY-231** `elmos-native-ub-sanitizer-orchestrator` — Run sanitizer/interpreter profiles such as ASan/UBSan/TSan/Miri or route-equivalent tools and turn findings into conversion blockers/evidence.
- **ELMOS-POLY-232** `elmos-runtime-edge-semantics-gate` — Aggregate memory, ABI, concurrency, numeric, temporal, encoding, wire, SQL and UB obligations before behavioral equivalence can pass.

### Batch {b} ({batch_counts[b]})
- **ELMOS-POLY-233** `elmos-observable-behavior-specification` — Define route-specific observables and comparison relations so equivalence means the same externally relevant behavior, not identical implementation.
- **ELMOS-POLY-234** `elmos-input-domain-partitioner` — Partition valid, invalid, boundary, adversarial and environment-dependent inputs from source contracts and traces to drive complete equivalence tests.
- **ELMOS-POLY-235** `elmos-semantic-golden-master-capture` — Capture source outputs, traces and state snapshots with normalization and provenance as replayable baseline evidence.
- **ELMOS-POLY-236** `elmos-multi-oracle-differential-executor` — Execute source and target under matched inputs/environments and compare multiple independent observables instead of stdout-only diffs.
- **ELMOS-POLY-237** `elmos-cross-runtime-trace-alignment` — Align semantically corresponding calls/events/transactions across structurally different runtimes using stable semantic event identities.
- **ELMOS-POLY-238** `elmos-state-snapshot-equivalence` — Compare selected object/heap/session state under canonical schemas while ignoring approved representation-only differences.
- **ELMOS-POLY-239** `elmos-database-state-equivalence` — Compare committed database state, constraints, keys, isolation outcomes and audit effects across source and target executions.
- **ELMOS-POLY-240** `elmos-message-event-equivalence` — Compare queues, topics, event envelopes, ordering, delivery semantics and deduplication outcomes.
- **ELMOS-POLY-241** `elmos-file-network-sideeffect-equivalence` — Compare filesystem and network effects including paths, bytes, status codes, headers, retries and external call contracts.
- **ELMOS-POLY-242** `elmos-api-contract-behavior-equivalence` — Verify status/error mapping, validation, pagination, authentication, compatibility and schema behavior at public APIs.
- **ELMOS-POLY-243** `elmos-ui-interaction-equivalence` — Compare user-visible workflows, navigation, form validation, accessibility-critical state and UI-triggered side effects across frameworks.
- **ELMOS-POLY-244** `elmos-performance-complexity-equivalence` — Detect asymptotic regressions and material latency/throughput/resource changes under statistically valid route-specific budgets.
- **ELMOS-POLY-245** `elmos-security-policy-equivalence` — Verify authentication, authorization, input handling, cryptographic policy and security-relevant defaults remain at least as strong after conversion.
- **ELMOS-POLY-246** `elmos-deterministic-replay-oracle` — Record and replay external nondeterministic inputs and schedules where possible to turn flaky differential failures into reproducible evidence.
- **ELMOS-POLY-247** `elmos-semantic-refinement-counterexample` — Judge target behavior as equality/refinement under the declared relation and emit minimal counterexamples for violations.
- **ELMOS-POLY-248** `elmos-behavior-equivalence-verdict-aggregator` — Aggregate all behavioral, state, side-effect, performance and security oracles into scoped pass/fail/blocked/waived verdicts with evidence freshness checks.

### Batch {b} ({batch_counts[b]})
- **ELMOS-POLY-249** `elmos-fixture-corpus-governance` — Define ownership, provenance, licensing, sensitivity, versioning and reproducibility rules for real/open/commercial fixture corpora.
- **ELMOS-POLY-250** `elmos-public-fixture-license-provenance` — Track repository origin, commit, license, redistribution constraints and transformations for public/open-source certification fixtures.
- **ELMOS-POLY-251** `elmos-language-spec-conformance-mapper` — Map normative language/runtime specification clauses and official conformance tests to ELMOS semantic features and route obligations.
- **ELMOS-POLY-252** `elmos-grammar-feature-coverage` — Measure parser/converter coverage over grammar productions, dialect extensions and syntactic combinations rather than file count.
- **ELMOS-POLY-253** `elmos-semantic-feature-coverage` — Measure route corpus coverage of type, control-flow, runtime, effect and behavior semantic obligations.
- **ELMOS-POLY-254** `elmos-dialect-version-fixture-matrix` — Maintain representative fixtures across language editions, vendor compilers, compatibility modes and framework/runtime versions.
- **ELMOS-POLY-255** `elmos-adversarial-edge-case-corpus` — Curate boundary and pathological programs that stress parsing, typing, UB, concurrency, numeric, encoding and reflection semantics.
- **ELMOS-POLY-256** `elmos-legacy-business-pattern-corpus` — Curate realistic batch, transaction, screen, record, report, decimal and procedural patterns from COBOL/RPG/PL/I/4GL estates.
- **ELMOS-POLY-257** `elmos-golden-route-repository-fixtures` — Build small/medium/large repository fixtures for every high-value Golden Route with source-native builds, tests and expected evidence.
- **ELMOS-POLY-258** `elmos-generated-program-corpus` — Generate semantically valid random programs and structured inputs to explore compiler/converter behavior beyond hand-authored fixtures.
- **ELMOS-POLY-259** `elmos-bug-regression-corpus` — Promote every confirmed semantic mismatch, compiler bug and production incident into a minimized permanent regression fixture.
- **ELMOS-POLY-260** `elmos-fixture-minimizer-deduplicator` — Reduce failing fixtures while preserving the failure oracle and deduplicate semantically equivalent corpus items to control certification cost.
- **ELMOS-POLY-261** `elmos-corpus-drift-freshness-manager` — Detect stale toolchain/spec/framework fixtures and schedule recertification when source standards, compilers or dependencies change.
- **ELMOS-POLY-262** `elmos-certification-corpus-readiness-gate` — Require sufficient syntax, semantic, dialect, adversarial, regression and scale coverage before a route can enter E4/E5 certification.

### Batch {b} ({batch_counts[b]})
- **ELMOS-POLY-263** `elmos-hermetic-toolchain-image-builder` — Build content-addressed toolchain/runtime images or VM descriptors with pinned compilers, SDKs, linkers, locale and OS dependencies.
- **ELMOS-POLY-264** `elmos-compiler-runtime-version-matrix` — Execute fixture suites across supported compiler/runtime versions and optimization modes to expose version-specific semantics.
- **ELMOS-POLY-265** `elmos-os-arch-libc-matrix` — Test platform-sensitive routes across OS, CPU architecture, endianness and libc/runtime implementations where semantics or ABI can differ.
- **ELMOS-POLY-266** `elmos-mainframe-native-runtime-lab` — Define controlled z/OS-style native execution for COBOL/PL/I/JCL/CICS/IMS/DB2 characterization and differential evidence.
- **ELMOS-POLY-267** `elmos-ibmi-native-runtime-lab` — Define controlled IBM i execution for RPG/CL/DDS/DB2 for i including library lists, job state, commitment control and object authority.
- **ELMOS-POLY-268** `elmos-windows-legacy-runtime-lab` — Provide isolated Windows environments for VB6/COM/ActiveX/PowerBuilder/Delphi/FoxPro behavior capture and migration verification.
- **ELMOS-POLY-269** `elmos-sap-abap-runtime-lab` — Define authorized SAP sandbox execution for ABAP/Open SQL/BAPI/RFC/IDoc/LUW behavior characterization without leaking customer systems.
- **ELMOS-POLY-270** `elmos-scientific-hpc-runtime-lab` — Execute Fortran/C/C++ numerical routes with BLAS/LAPACK/MPI/OpenMP/vectorization and deterministic numeric comparison profiles.
- **ELMOS-POLY-271** `elmos-mobile-native-runtime-lab` — Run Swift/Objective-C/Kotlin/Java/Flutter/React-derived mobile workloads across simulator/device profiles with lifecycle and platform-channel evidence.
- **ELMOS-POLY-272** `elmos-browser-js-wasm-runtime-lab` — Run ECMAScript/TypeScript/React/Wasm-related fixtures across major engines with conformance and portable-semantics checks.
- **ELMOS-POLY-273** `elmos-database-message-runtime-lab` — Provision real compatible database/message broker matrices for transaction, collation, delivery and retry equivalence instead of mocks-only certification.
- **ELMOS-POLY-274** `elmos-native-runtime-lab-evidence-attestor` — Bind runtime evidence to immutable image/VM, hardware, compiler, dependency, fixture, command and output identities and reject stale lab evidence.

### Batch {b} ({batch_counts[b]})
- **ELMOS-POLY-275** `elmos-formal-semantics-contract` — Define the source/target semantic relation, observable behavior domain, undefined behavior assumptions and proof scope before applying formal methods.
- **ELMOS-POLY-276** `elmos-translation-validation-planner` — Select per-function/module/route validation strategies such as refinement checking, symbolic execution, BMC or runtime differential evidence.
- **ELMOS-POLY-277** `elmos-llvm-ir-refinement-checker` — Lower suitable native-language fragments to LLVM IR and use refinement-style translation validation where source/target semantics can be represented safely.
- **ELMOS-POLY-278** `elmos-smt-equivalence-prover` — Encode bounded pure/finite semantic obligations into SMT and prove equivalence/refinement or return concrete counterexamples.
- **ELMOS-POLY-279** `elmos-symbolic-execution-equivalence` — Symbolically execute source/target paths for selected modules and compare path conditions, outputs and side effects under bounded models.
- **ELMOS-POLY-280** `elmos-bounded-model-checking-equivalence` — Check bounded loops/state machines/concurrency properties and source-target assertions with explicit bounds and counterexamples.
- **ELMOS-POLY-281** `elmos-abstract-interpretation-invariant-engine` — Infer ranges, nullness, alias/effect facts and invariants that strengthen conversion safety and reduce proof/testing search space.
- **ELMOS-POLY-282** `elmos-proof-obligation-generator` — Generate route-specific obligations from semantic IR, source contracts and target adaptations, with machine-readable status and dependency graphs.
- **ELMOS-POLY-283** `elmos-contract-invariant-inference` — Infer candidate preconditions, postconditions and invariants from code, traces and tests while distinguishing inferred hypotheses from proven contracts.
- **ELMOS-POLY-284** `elmos-verified-lowering-route` — Define high-assurance lowering paths where a verified compiler/intermediate target or proof-producing step can reduce the trusted computing base.
- **ELMOS-POLY-285** `elmos-wasm-portable-semantics-oracle` — Use WebAssembly’s specified validation/execution semantics and reference tests as an optional portable low-level oracle for suitable cross-language kernels.
- **ELMOS-POLY-286** `elmos-proof-counterexample-replayer` — Convert solver/model-checker/refinement counterexamples into executable regression tests in source and target environments when possible.
- **ELMOS-POLY-287** `elmos-proof-cache-invalidation` — Cache expensive proof/analysis results by source, IR, toolchain, solver and assumption identity and invalidate them on semantic drift.
- **ELMOS-POLY-288** `elmos-formal-assurance-gate` — Aggregate proof/refinement/model-checking evidence where required and combine it with runtime evidence without overclaiming unproved portions.

### Batch {b} ({batch_counts[b]})
- **ELMOS-POLY-289** `elmos-grammar-based-semantic-fuzzer` — Generate/mutate syntactically valid programs and inputs from grammar plus semantic constraints to stress parser and converter edges.
- **ELMOS-POLY-290** `elmos-coverage-guided-differential-fuzzer` — Use source/target coverage and behavioral disagreement as guidance to discover semantic conversion mismatches.
- **ELMOS-POLY-291** `elmos-metamorphic-transformation-tester` — Apply semantics-preserving source transformations and require conversion/output relations to remain stable without needing a perfect oracle.
- **ELMOS-POLY-292** `elmos-property-based-cross-language-tester` — Generate values/state sequences from contracts and assert language-independent properties across source and target implementations.
- **ELMOS-POLY-293** `elmos-compiler-matrix-nversion-oracle` — Compile/run fixtures with multiple independent compilers/runtimes to detect implementation-specific behavior and strengthen differential oracles.
- **ELMOS-POLY-294** `elmos-undefined-behavior-filter` — Exclude or explicitly model source cases whose behavior is undefined/unspecified before treating runtime disagreement as converter failure.
- **ELMOS-POLY-295** `elmos-semantic-mutation-testing` — Inject behavior-changing mutations into conversion rules/targets and verify that equivalence tests and oracles reliably kill them.
- **ELMOS-POLY-296** `elmos-equivalent-mutant-classifier` — Distinguish surviving equivalent/no-op mutations from weak tests using static, differential and bounded proof evidence where feasible.
- **ELMOS-POLY-297** `elmos-failure-reducer-minimizer` — Automatically minimize failing source programs, inputs, repository slices and traces while preserving the semantic mismatch oracle.
- **ELMOS-POLY-298** `elmos-flaky-nondeterminism-classifier` — Separate true semantic mismatches from scheduler, timing, network, hash-order and environment noise using replay and statistical evidence.
- **ELMOS-POLY-299** `elmos-bug-seed-feedback-loop` — Feed confirmed minimized failures into route rules, fixture corpora, mutation operators and risk models with provenance and regression guarantees.
- **ELMOS-POLY-300** `elmos-semantic-stress-certification-gate` — Require differential fuzzing, metamorphic/property testing, mutation strength and failure reduction thresholds appropriate to route risk before E4/E5.
