# Project Synthesis capability map

Use the canonical specifications under `elmos-project-synthesis-batch46-60/skills` for global PG001–PG170, `elmos-project-synthesis-batch61-65/skills` for global PG171–PG222, `elmos-codex-skills-batch66-80-complete/skills` for global PG223–PG417, and `elmos-language-packs-batch81-95-complete/skills` for the separate package-local PG223–PG402 namespace. Search the applicable manifest or `index.json`, then read only the selected specifications and dependencies. Never infer global continuity across the Language Pack source IDs; use the installed `$b81-*`–`$b95-*` alias and `LP-Bxx-PGxxx` source key.

| Phase | Batch / PG | Required result |
|---|---|---|
| Constitution, API, PSIR, evidence | 46 / PG001–PG010 | Governed run and typed canonical inputs |
| Natural-language discovery | 47 / PG011–PG020 | Versioned requirement workspace with provenance and questions |
| Requirement quality and approval | 48 / PG021–PG032 | Immutable question-free requirement baseline |
| Domain model and traceability | 49 / PG033–PG042 | Domain specification and testable behavior |
| Architecture | 50 / PG043–PG054 | Approved architecture baseline and threats/tradeoffs |
| Exact project blueprint | 51 / PG055–PG064 | Runtime, framework, dependency, layout, build, config, quality locks |
| Deterministic generation | 52 / PG065–PG076 | Semantic code model, ownership, stable generation manifest and SBOM |
| Java | 53 / PG077–PG088 | Spring Boot/Java project pack |
| Python | 54 / PG089–PG100 | FastAPI/Django/Python project pack |
| C# / .NET | 55 / PG101–PG112 | ASP.NET Core/.NET project pack |
| Database and integration | 56 / PG113–PG124 | Data, migration, API, messaging, resilience and contract assets |
| Frontend/full-stack | 57 / PG125–PG134 | Frontend and end-to-end wiring |
| Tests | 58 / PG135–PG146 | Requirement-traced unit through nonfunctional tests |
| Build, startup and bounded repair | 59 / PG147–PG158 | Clean build evidence, health probes and safe repair |
| DevSecOps and delivery | 60 / PG159–PG170 | CI, secrets policy, hardening, observability, rollout and recovery |
| Safe change and regeneration | 61 / PG171–PG180 | Drift detection, protected manual edits, bounded regeneration, compatibility, approval and PR delivery |
| Agent and Skill runtime | 62 / PG181–PG190 | Separated agent roles, contract routing, sandboxes, budgets, Domain Pack SDK and compatibility |
| Product evaluation | 63 / PG191–PG202 | Independent requirements-through-chaos evaluation and fail-closed product certification |
| Industry Domain Packs | 64 / PG203–PG212 | Versioned policy-safe domain models for ten industry/application profiles |
| Requirement Studio operations | 65 / PG213–PG222 | Review UI, diffs, run/evidence consoles, collaboration, quotas, metering, diagnostics and governed feedback |
| TypeScript / JavaScript | 66 / PG223–PG234 | Exact Node, monorepo, API, web, worker, data, contract, test and build/run profile |
| Go | 67 / PG235–PG246 | Modules, services, CLI, workers, concurrency, operators, MCP, tests and cross-compilation |
| Kotlin | 68 / PG247–PG258 | JVM, Spring, Ktor, coroutines, persistence, interop, Android, multiplatform and build/run profile |
| PHP | 69 / PG259–PG270 | Composer, Laravel, Symfony, monolith, persistence, queues, CMS, tests, repair and deployment |
| C / C++ native | 70 / PG271–PG284 | Toolchain, CMake, ABI/FFI, memory/concurrency, ROS 2, OPC UA, embedded, Qt, sanitizers and runtime evidence |
| Rust | 71 / PG285–PG296 | Cargo, services, CLI/workers, Serde, FFI/WASM, unsafe and supply-chain review, fuzzing and release |
| Dart / Flutter | 72 / PG297–PG308 | Multiplatform architecture, state/routing, API/offline, channels, UI/a11y, tests, signing and runtime evidence |
| Swift / Apple | 73 / PG309–PG320 | SwiftUI, Xcode/SwiftPM, state, network, persistence, concurrency, interop, widgets, a11y, XCTest and signing |
| Shell / PowerShell | 74 / PG321–PG334 | Cross-shell parsing, arguments, error/process handling, remoting, secrets, signing, linting and tests |
| SQL and API contracts | 75 / PG335–PG350 | SQL dialect/data/transaction/performance/security plus OpenAPI, Protobuf, GraphQL and compatibility |
| Build and proxy configuration | 76 / PG351–PG362 | Make/CMake graphs and Nginx routing, TLS, limits, hardening, tests and configuration evidence |
| Containers | 77 / PG363–PG374 | Docker/Compose builds, multi-architecture, rootless hardening, SBOM, health, topology, parity and runtime evidence |
| IaC / Kubernetes / Helm | 78 / PG375–PG390 | Terraform/OpenTofu state/plan/policy/cost/drift, Kubernetes/Helm/admission/GitOps and rollback evidence |
| CI/CD | 79 / PG391–PG405 | GitHub Actions, GitLab CI, Jenkins, runner/OIDC/permission/cache/environment/release/provenance evidence |
| Polyglot operations | 80 / PG406–PG417 | Cross-language asset graph, orchestration, synchronized contracts, parity, identity, provenance, replay, repair and final gate |
| COBOL / Mainframe | 81 / source PG223–PG234 | Estate, COBOL/copybook/JCL/CICS/IMS semantics, data, rules, adapters, parallel run, security and cutover |
| SAP ABAP | 82 / source PG235–PG246 | SAP landscape, ABAP/CDS/RAP, BAPI/RFC/IDoc, UI, clean core, data, tests, BTP and transport/cutover |
| Database procedural | 83 / source PG247–PG258 | PL/SQL, T-SQL, PL/pgSQL, SQL PL semantics, dynamic SQL, retain/extract decisions, tests and transaction equivalence |
| IEC 61131-3 PLC | 84 / source PG259–PG270 | PLC languages, task/scan/IO/state semantics, vendor adapters, simulation, OPC UA, SIL approval and deployment |
| MATLAB / Simulink | 85 / source PG271–PG282 | MATLAB, Simulink, Stateflow, Simscape, interop, codegen, SIL/PIL/HIL, numerical equivalence and traceability |
| Modelica / FMI | 86 / source PG283–PG294 | Physical models, equation/unit/event semantics, FMU, co-simulation, calibration, regression, drift and runtime evidence |
| VB / Office | 87 / source PG295–PG306 | VB6/VBA/VB.NET, COM, forms/events, Office automation, bitness, generators, regression and modernization evidence |
| IBM i RPG | 88 / source PG307–PG318 | RPG/CL/DDS/DB2 for i, record/decimal/commitment/job semantics, services, parallel run and cutover |
| R data science | 89 / source PG319–PG330 | R/Quarto/Shiny/renv, data/model/report reproducibility, package isolation, tests and statistical evidence |
| SAS | 90 / source PG331–PG342 | SAS/Macro/PROC SQL/Viya estate, datasets, programs, jobs, migration and dataset/statistic/report equivalence |
| Salesforce | 91 / source PG343–PG354 | Apex/SOQL/LWC, org metadata, security/sharing/governor limits, integration, tests and release evidence |
| Objective-C / Swift | 92 / source PG355–PG366 | Objective-C runtime, Cocoa, ownership, interop, Swift migration, UI/data/concurrency, binary/API compatibility and cutover |
| Delphi / Object Pascal | 93 / source PG367–PG378 | Pascal semantics, VCL/FMX, packages, data/hardware integration, migration, regression and target-device evidence |
| BEAM | 94 / source PG379–PG390 | Erlang/Elixir/Gleam, OTP/supervision/distribution, messaging, upgrades, partitions/overload and release evidence |
| Lua / OpenResty | 95 / source PG391–PG402 | Lua/OpenResty/embedded scripting, sandboxing, resources, gateway/plugin behavior, tests and deployment evidence |

The repository engine currently provides a conservative runnable starter profile: one primary CRUD aggregate, Java 21/Spring Boot 3.5.3, Python 3.12/FastAPI 0.116.1, and .NET 10/ASP.NET Core. It emits configuration, tests, OpenAPI, CI, non-root containers, Kubernetes, traceability and a content-addressed manifest. Batch 66–95 expands governed Skill routing and exact evidence contracts; it does not silently expand the bundled emitter. Batch 81–95 source IDs are package-local and overlap the global PG sequence. Other languages/assets, vendor platforms, physical systems, durable databases, deployment, cutover and production certification require explicit selected Skills, real native tools/environments, safety approval and external evidence.
