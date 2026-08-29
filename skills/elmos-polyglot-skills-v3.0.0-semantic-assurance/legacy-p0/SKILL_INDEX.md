# ELMOS Legacy P0 Skill Index

Total: **104 Skills**.

## Batch E — Foundation / IR / Planning

- `ELMOS-POLY-065` **elmos-legacy-p0-orchestrator** — Coordinate P0 legacy repository discovery, semantic lowering, target selection, conversion, coexistence, verification, evidence, and cutover.
- `ELMOS-POLY-066` **elmos-legacy-repository-archeologist** — Recover code, copybooks, job control, screens, binary assets, schemas, generated artifacts, runtime dependencies, and operational knowledge from legacy repositories.
- `ELMOS-POLY-067` **elmos-source-encoding-normalizer** — Detect and normalize EBCDIC/code pages, newline modes, tab/column rules, source encodings, and binary/text boundaries without losing byte provenance.
- `ELMOS-POLY-068` **elmos-fixed-format-source-normalizer** — Normalize fixed-column, sequence-area, continuation, indicator, and card-image source forms into reversible logical source while preserving original coordinates.
- `ELMOS-POLY-069` **elmos-legacy-build-runtime-discovery** — Recover unavailable or implicit compilers, linkers, preprocessors, subsystem versions, copy/include paths, runtime libraries, database clients, job schedulers, and deployment assumptions.
- `ELMOS-POLY-070` **elmos-legacy-dependency-runtime-graph** — Build symbol, include/copy, call, job-step, data, transaction, screen, dataset, program-to-program, remote-call, and runtime integration graphs.
- `ELMOS-POLY-071` **elmos-business-rule-ir-builder** — Extract auditable business rules from procedural, 4GL, screen, job and database logic with source spans, predicates, effects, priority and exception semantics.
- `ELMOS-POLY-072` **elmos-record-layout-ir-builder** — Model COBOL/RPG/PL-I/Fortran/Pascal/xBase record layout, decimal formats, overlays, unions, variable arrays, alignment and physical byte representation.
- `ELMOS-POLY-073` **elmos-transaction-ir-builder** — Recover transaction boundaries, commit/backout, lock scope, update tasks, unit-of-work, retry and idempotency semantics across legacy runtimes.
- `ELMOS-POLY-074` **elmos-batch-job-ir-builder** — Model JCL, CL, schedulers, steps, datasets, temporary files, return-code branches, checkpoints, restartability and batch SLA semantics.
- `ELMOS-POLY-075` **elmos-screen-workflow-ir-builder** — Recover terminal, desktop and 4GL screen navigation, state, validation, field protection, events, menu/action flows and user-visible error behavior.
- `ELMOS-POLY-076` **elmos-indexed-file-state-ir-builder** — Model VSAM, DBF/CDX, keyed/relative files, DDS physical/logical files and other indexed storage as logical state plus physical semantics.
- `ELMOS-POLY-077` **elmos-numerical-ir-builder** — Extract numerical kernels, array/storage order, precision, BLAS/LAPACK calls, loop transformations and tolerated error envelopes for scientific conversion.
- `ELMOS-POLY-078` **elmos-safety-contract-ir-builder** — Extract range constraints, contracts, assertions, real-time deadlines, tasking assumptions and proof obligations from C/Ada/SPARK and safety-critical code.
- `ELMOS-POLY-079` **elmos-legacy-control-flow-ir-builder** — Normalize GO TO, PERFORM ranges, ALTER, computed branches, error labels, event callbacks and irreducible control flow into explicit CFG/state-machine representations.
- `ELMOS-POLY-080` **elmos-enterprise-4gl-ir-builder** — Model DataWindow, ABAP internal tables/Open SQL, Natural database loops, ABL buffers/temp-tables, FoxPro work areas and other 4GL high-level behaviors.
- `ELMOS-POLY-081` **elmos-native-abi-ir-builder** — Capture native ABI, calling conventions, packing, symbol export, COM interfaces, callbacks, FFI, binary structures and cross-language ownership.
- `ELMOS-POLY-082` **elmos-semantic-loss-risk-estimator** — Score semantic loss per symbol, module and route, including money, data integrity, security, concurrency, numerical, ABI and safety consequences.
- `ELMOS-POLY-083` **elmos-target-fitness-route-scorer** — Rank destination languages/stacks by semantic fit, performance, operations, ecosystem, team constraints, coexistence and verification cost; reject low-fitness blind conversions.
- `ELMOS-POLY-084` **elmos-coexistence-strangler-planner** — Plan API wrapping, dual run, data replication, batch coexistence, module strangulation, rollback, cutover and decommissioning for incremental legacy modernization.

## Batch F — P0 Language + Repository Adapters

- `ELMOS-POLY-085` **elmos-adapter-c** — Implement C language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-086` **elmos-adapter-cobol** — Implement COBOL language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-087` **elmos-adapter-rpg** — Implement RPG/RPGLE language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-088` **elmos-adapter-pli** — Implement PL/I language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-089` **elmos-adapter-vb6** — Implement Visual Basic 6 language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-090` **elmos-adapter-vbscript** — Implement VBScript language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-091` **elmos-adapter-object-pascal** — Implement Object Pascal/Delphi language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-092` **elmos-adapter-powerscript** — Implement PowerScript/PowerBuilder language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-093` **elmos-adapter-abap** — Implement ABAP language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-094` **elmos-adapter-natural** — Implement Natural language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-095` **elmos-adapter-abl** — Implement Progress OpenEdge ABL language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-096` **elmos-adapter-fortran** — Implement Fortran language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-097` **elmos-adapter-ada-spark** — Implement Ada/SPARK language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-098` **elmos-adapter-xbase** — Implement xBase/FoxPro language parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-099` **elmos-adapter-jcl** — Implement JCL repository-dsl parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-100` **elmos-adapter-rexx** — Implement REXX repository-dsl parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-101` **elmos-adapter-ibmi-cl** — Implement IBM i CL/CLLE repository-dsl parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-102` **elmos-adapter-cobol-copybook** — Implement COBOL Copybook repository-dsl parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-103` **elmos-adapter-cics-bms** — Implement CICS BMS repository-dsl parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-104` **elmos-adapter-ims-mfs** — Implement IMS MFS repository-dsl parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-105` **elmos-adapter-ibmi-dds** — Implement IBM i DDS repository-dsl parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.
- `ELMOS-POLY-106` **elmos-adapter-legacy-sql-routines** — Implement Legacy SQL/Routine Surface repository-dsl parsing, semantic lowering, framework/runtime mapping, target emission and verification for repository-scale modernization.

## Batch G — Legacy Semantic Transformations

- `ELMOS-POLY-107` **elmos-character-encoding-transcoder** — Convert EBCDIC/code pages/Unicode and text-vs-binary records with reversible byte provenance and field-level validation.
- `ELMOS-POLY-108` **elmos-decimal-arithmetic-preserver** — Preserve packed/zoned/fixed decimal precision, rounding, overflow, scale, currency and financial arithmetic across target numeric models.
- `ELMOS-POLY-109` **elmos-record-layout-mapper** — Map overlays, REDEFINES, unions, packed records, variable arrays and alignment into safe target schemas without silently changing bytes.
- `ELMOS-POLY-110` **elmos-indexed-file-database-migrator** — Migrate VSAM/DBF/DDS/indexed files to relational/document/KV stores while preserving keys, collation, duplicates, ordering and restart semantics.
- `ELMOS-POLY-111` **elmos-embedded-sql-routine-migrator** — Extract and convert embedded SQL, cursors, stored procedures, triggers, SQL dialects and host-variable semantics into approved target data access.
- `ELMOS-POLY-112` **elmos-transaction-monitor-migrator** — Map CICS/IMS/SAP LUW/OpenEdge/IBM i transaction behavior to explicit modern units of work, retries, outbox/saga patterns and rollback.
- `ELMOS-POLY-113` **elmos-batch-scheduler-migrator** — Convert JCL/CL/legacy schedulers into workflow/job definitions while preserving dependencies, datasets, return codes, checkpoints and restart.
- `ELMOS-POLY-114` **elmos-terminal-screen-ui-migrator** — Convert BMS/MFS/DDS/Dynpro/Natural maps and terminal workflows to web/API UI while preserving navigation, validation and accessibility semantics.
- `ELMOS-POLY-115` **elmos-report-printer-migrator** — Convert printer files, VFP/PowerBuilder/legacy reports and spool workflows to report services/PDF/export pipelines with layout regression tests.
- `ELMOS-POLY-116` **elmos-legacy-messaging-migrator** — Map MQ, CICS/IMS messaging, SAP IDoc/RFC/BAPI and file-based interchange to modern messaging/API contracts with delivery guarantees.
- `ELMOS-POLY-117` **elmos-mainframe-security-migrator** — Translate RACF/ACF2/Top Secret/Natural/SAP/IBM i authority concepts to explicit IAM/RBAC/ABAC mappings without privilege broadening.
- `ELMOS-POLY-118` **elmos-c-memory-safety-migrator** — Transform C ownership, pointer arithmetic, allocation and lifetime patterns toward Rust/C++ safety models using evidence-backed unsafe boundaries.
- `ELMOS-POLY-119` **elmos-native-abi-ffi-migrator** — Preserve ABI/FFI/COM/native calling conventions, symbol contracts, callback lifetime and binary layout through wrappers or generated bindings.
- `ELMOS-POLY-120` **elmos-numerical-kernel-migrator** — Transform Fortran/C numerical kernels to C++/Rust/Python-native stacks while preserving vectorization, libraries, memory order and computational complexity.
- `ELMOS-POLY-121` **elmos-floating-point-equivalence-controller** — Define route-specific floating-point tolerances, reproducibility modes, reduction-order controls and high-precision oracle comparisons.
- `ELMOS-POLY-122` **elmos-safety-realtime-migrator** — Preserve Ada/SPARK/C real-time scheduling, deadlines, boundedness, representation and safety contracts when moving to Rust/C++/Ada targets.
- `ELMOS-POLY-123` **elmos-com-activex-ole-migrator** — Inventory and replace/wrap COM, ActiveX, OLE Automation, type libraries, apartment models and registration dependencies during Windows modernization.
- `ELMOS-POLY-124` **elmos-desktop-ui-migrator** — Transform VB6/Delphi/VFP desktop forms, event lifecycles, controls and resources to approved C#/web targets with workflow characterization.
- `ELMOS-POLY-125` **elmos-powerbuilder-datawindow-migrator** — Decompose DataWindow SQL, binding, validation, update rules, presentation and events into explicit API/data/UI components.
- `ELMOS-POLY-126` **elmos-sap-business-object-migrator** — Extract ABAP DDIC/CDS, Open SQL, internal tables, BAPI/RFC/IDoc, enhancements and authorization behavior into target domain/integration models.
- `ELMOS-POLY-127` **elmos-natural-adabas-migrator** — Transform Natural programs/maps/DDMs and Adabas multivalue/periodic-group semantics into explicit application/data models.
- `ELMOS-POLY-128` **elmos-openedge-abl-migrator** — Transform ABL buffers, temp-tables, procedures/classes, handles, transactions and PASOE integration to explicit modern service/data layers.
- `ELMOS-POLY-129` **elmos-ibmi-rpg-db2i-migrator** — Transform RPG opcodes/indicators, DB2 for i record IO, DDS/SQL, CL integration and activation-group behavior into target services.
- `ELMOS-POLY-130` **elmos-xbase-dbf-index-migrator** — Transform xBase/FoxPro work areas, DBF/CDX indexes, SET state, macros, forms and reports into explicit services/data/UI modules.

## Batch H — Reference Golden Routes

- `ELMOS-POLY-131` **elmos-mainframe-cobol-to-java-golden-route** — Execute the reference route: COBOL/CICS/DB2/VSAM/JCL to Java/Spring Boot.
- `ELMOS-POLY-132` **elmos-mainframe-cobol-to-csharp-golden-route** — Execute the reference route: COBOL/CICS/DB2/VSAM/JCL to C#/ASP.NET Core.
- `ELMOS-POLY-133` **elmos-ibmi-rpg-to-java-golden-route** — Execute the reference route: RPG/RPGLE/CL/DDS/DB2 for i to Java/Spring Boot.
- `ELMOS-POLY-134` **elmos-ibmi-rpg-to-csharp-golden-route** — Execute the reference route: RPG/RPGLE/CL/DDS/DB2 for i to C#/ASP.NET Core.
- `ELMOS-POLY-135` **elmos-pli-to-java-golden-route** — Execute the reference route: PL/I mainframe applications to Java/Spring.
- `ELMOS-POLY-136` **elmos-pli-to-csharp-golden-route** — Execute the reference route: PL/I mainframe applications to C#/ASP.NET Core.
- `ELMOS-POLY-137` **elmos-vb6-to-csharp-golden-route** — Execute the reference route: VB6/COM desktop applications to C# with staged UI and COM replacement.
- `ELMOS-POLY-138` **elmos-vbscript-to-csharp-golden-route** — Execute the reference route: VBScript/Classic ASP automation and web code to modern .NET.
- `ELMOS-POLY-139` **elmos-powerbuilder-to-csharp-react-golden-route** — Execute the reference route: PowerBuilder/DataWindow to ASP.NET Core plus React-compatible API/UI model.
- `ELMOS-POLY-140` **elmos-delphi-to-csharp-golden-route** — Execute the reference route: Delphi/Object Pascal/VCL to C# desktop or service architecture.
- `ELMOS-POLY-141` **elmos-abap-to-java-golden-route** — Execute the reference route: ABAP business logic/integration to Java/Spring with SAP coexistence.
- `ELMOS-POLY-142` **elmos-natural-adabas-to-java-golden-route** — Execute the reference route: Natural/Adabas to Java/Spring and modern database.
- `ELMOS-POLY-143` **elmos-abl-openedge-to-java-golden-route** — Execute the reference route: OpenEdge ABL/PASOE to Java/Spring.
- `ELMOS-POLY-144` **elmos-c-to-rust-golden-route** — Execute the reference route: C native/embedded modules to Rust with memory-safety proof obligations.
- `ELMOS-POLY-145` **elmos-c-to-cpp-modernization-route** — Execute the reference route: C to modern C++ with ABI and ownership preservation.
- `ELMOS-POLY-146` **elmos-ada-spark-to-rust-golden-route** — Execute the reference route: Ada/SPARK to Rust for safety-oriented native modernization.
- `ELMOS-POLY-147` **elmos-rust-to-ada-spark-assurance-route** — Execute the reference route: Rust to Ada/SPARK where stronger contract/proof regimes are required.
- `ELMOS-POLY-148` **elmos-fortran-to-cpp-golden-route** — Execute the reference route: Fortran numerical/HPC code to modern C++.
- `ELMOS-POLY-149` **elmos-fortran-to-python-numerical-route** — Execute the reference route: Fortran to Python scientific stack while retaining native kernels where required.
- `ELMOS-POLY-150` **elmos-xbase-foxpro-to-csharp-golden-route** — Execute the reference route: FoxPro/xBase DBF/forms/reports to C#/ASP.NET or desktop target.
- `ELMOS-POLY-151` **elmos-cobol-in-place-modernization-route** — Execute the reference route: COBOL dialect/source modernization before or instead of replatforming.
- `ELMOS-POLY-152` **elmos-rpg-in-place-modernization-route** — Execute the reference route: Fixed-format RPG to free-form/modular/API-enabled RPG modernization.

## Batch I — Validation / Certification

- `ELMOS-POLY-153` **elmos-parser-ast-conformance-validator** — Compare native compiler/parser results, symbols and source spans against adapter output on dialect/version fixture matrices.
- `ELMOS-POLY-154` **elmos-byte-record-layout-validator** — Verify record sizes, offsets, overlays, packed fields, alignment, encodings and round-trip bytes between source and target representations.
- `ELMOS-POLY-155` **elmos-decimal-financial-equivalence-validator** — Verify decimal precision, scale, rounding, overflow and monetary results using high-precision or source-runtime oracles.
- `ELMOS-POLY-156` **elmos-transaction-commit-rollback-validator** — Replay success, failure, retry and partial-update scenarios to prove equivalent commit, rollback, locking and idempotency behavior.
- `ELMOS-POLY-157` **elmos-batch-order-restart-validator** — Verify job ordering, return-code branching, dataset lifecycle, checkpoints, restart and exactly-once/at-least-once side-effect semantics.
- `ELMOS-POLY-158` **elmos-ui-workflow-equivalence-validator** — Replay terminal/desktop/web user journeys and compare navigation, field validation, authorization, errors and persistent effects.
- `ELMOS-POLY-159` **elmos-indexed-file-data-validator** — Reconcile source indexed files and target stores for key semantics, collation, duplicates, ordering, tombstones and full dataset checksums.
- `ELMOS-POLY-160` **elmos-sql-result-equivalence-validator** — Compare query/routine results, null/collation/date behavior, isolation and side effects across database dialects and access layers.
- `ELMOS-POLY-161` **elmos-numerical-tolerance-validator** — Validate numerical outputs across representative and adversarial datasets using declared absolute/relative/ULP tolerances and performance budgets.
- `ELMOS-POLY-162` **elmos-native-abi-behavior-validator** — Verify exported symbols, calling conventions, struct layout, callbacks, FFI ownership and binary interop across source/target builds.
- `ELMOS-POLY-163` **elmos-memory-safety-regression-validator** — Run sanitizers, Miri/fuzzing/static analysis and leak/use-after-free/double-free fixtures for C/C++/Rust conversion routes.
- `ELMOS-POLY-164` **elmos-safety-contract-proof-validator** — Check SPARK/GNATprove or equivalent contracts, assertions, ranges, WCET/deadline evidence and approved proof waivers for safety routes.
- `ELMOS-POLY-165` **elmos-legacy-performance-capacity-validator** — Compare batch elapsed time, throughput, latency, memory, CPU, IO and peak-volume behavior against declared SLO/budget envelopes.
- `ELMOS-POLY-166` **elmos-security-authority-equivalence-validator** — Prove identities, roles, authorities, segregation-of-duties and denied operations are not broadened during migration.
- `ELMOS-POLY-167` **elmos-dual-run-shadow-reconciliation-validator** — Operate source and target in shadow/dual-run, normalize nondeterminism, reconcile outputs/state and quantify divergence before cutover.
- `ELMOS-POLY-168` **elmos-legacy-production-certification-gate** — Issue E0-E5-style readiness only from fresh executed evidence, with explicit blockers, waivers, rollback readiness and route-specific residual risk.

