# Skill Catalog

| ID | Batch | Skill | Purpose |
|---|---:|---|---|
| PG033 | 49 | `user-story-and-use-case-builder` | Translate approved requirements into behavior-centered specifications that can drive domain modeling and acceptance tests. |
| PG034 | 49 | `business-rule-modeler` | Create an executable-quality business rule model independent of programming language and framework. |
| PG035 | 49 | `domain-entity-value-object-modeler` | Create a language-neutral domain model grounded in business behavior rather than database tables. |
| PG036 | 49 | `bounded-context-candidate-builder` | Create candidate domain boundaries before architecture decomposition. |
| PG037 | 49 | `domain-event-command-query-modeler` | Express domain behavior as explicit intent, information requests, and state-change facts. |
| PG038 | 49 | `workflow-and-state-machine-modeler` | Make lifecycle behavior explicit enough for implementation and verification. |
| PG039 | 49 | `data-dictionary-builder` | Create a semantic data contract shared by domain, API, persistence, analytics, and security planning. |
| PG040 | 49 | `api-contract-draft-builder` | Create reviewable interface intent before selecting implementation frameworks. |
| PG041 | 49 | `permission-matrix-builder` | Turn authorization expectations into an explicit and testable access model. |
| PG042 | 49 | `requirement-traceability-graph` | Provide completeness checks and impact analysis before architecture planning. |
| PG043 | 50 | `architecture-style-selector` | Choose the simplest architecture style that satisfies approved requirements and policy. |
| PG044 | 50 | `system-context-container-planner` | Define system boundaries, users, external systems, deployable units, data stores, and trust zones. |
| PG045 | 50 | `module-and-service-decomposer` | Produce cohesive implementation boundaries while minimizing distributed coupling and operational cost. |
| PG046 | 50 | `quality-attribute-tradeoff-analyzer` | Make architecture tradeoffs explicit instead of hiding them inside framework choices. |
| PG047 | 50 | `data-ownership-consistency-planner` | Prevent ambiguous data authority and unsafe cross-module transactions. |
| PG048 | 50 | `sync-async-communication-planner` | Match communication semantics to business timing, coupling, reliability, throughput, and observability needs. |
| PG049 | 50 | `resilience-and-failure-mode-planner` | Ensure deliberate behavior under dependency, infrastructure, capacity, data, and operator failures. |
| PG050 | 50 | `security-and-threat-model-planner` | Integrate security design before implementation generation. |
| PG051 | 50 | `multitenancy-topology-planner` | Select an explicit tenant topology when the product requires tenant separation. |
| PG052 | 50 | `observability-architecture-planner` | Make runtime behavior diagnosable before source generation. |
| PG053 | 50 | `deployment-topology-planner` | Translate runtime architecture into an operable deployment design. |
| PG054 | 50 | `adr-and-architecture-review-pack` | Produce the immutable architecture baseline consumed by Project Blueprint compilation. |
| PG055 | 51 | `application-profile-selector` | Turn the Architecture Baseline into concrete deployable application profiles. |
| PG056 | 51 | `language-framework-profile-selector` | Choose implementation technology from approved constraints and supported Golden Paths. |
| PG057 | 51 | `runtime-version-policy-resolver` | Pin supported versions without floating latest tags or hidden compatibility assumptions. |
| PG058 | 51 | `dependency-catalog-and-bom-planner` | Make third-party dependency selection controlled, minimal, and reproducible. |
| PG059 | 51 | `repository-layout-planner` | Create a repository layout aligned with architecture, build graph, and regeneration boundaries. |
| PG060 | 51 | `namespace-and-package-planner` | Ensure generated identifiers are stable, valid, consistent, and traceable across languages and tools. |
| PG061 | 51 | `build-system-planner` | Create a build contract that works in a clean environment without hidden developer-machine state. |
| PG062 | 51 | `environment-configuration-planner` | Define safe configuration behavior without embedding environment-specific or secret values in source. |
| PG063 | 51 | `code-style-and-quality-profile` | Create enforceable source-quality rules before code generation. |
| PG064 | 51 | `project-blueprint-compiler` | Produce the only approved input to common and language-specific code-generation engines. |
| PG065 | 52 | `template-registry` | Provide governed template discovery, compatibility, deprecation, and versioning for common generation. |
| PG066 | 52 | `template-signing-and-provenance` | Prevent untrusted, revoked, or silently modified templates from entering generation. |
| PG067 | 52 | `semantic-code-model` | Bridge Project Blueprint intent to target-language AST/CST generation without relying on raw string concatenation. |
| PG068 | 52 | `scaffold-composer` | Create the complete initial project skeleton according to the approved Project Blueprint. |
| PG069 | 52 | `ast-cst-code-emitter` | Generate structured code while preserving syntax correctness, symbol identity, formatting hooks, traceability, and merge safety. |
| PG070 | 52 | `configuration-file-emitter` | Produce valid configuration artifacts through schema-aware, parser-aware, and policy-aware generation. |
| PG071 | 52 | `generated-file-ownership` | Define exactly what future regeneration may replace, merge, preserve, or only inspect. |
| PG072 | 52 | `protected-region-and-extension-point` | Provide safe customization points without forcing users to fork managed source. |
| PG073 | 52 | `idempotent-generation-engine` | Make repeated generation safe for CI, retries, branch refreshes, and incremental development. |
| PG074 | 52 | `incremental-merge-engine` | Update generated projects safely after Blueprint or requirement changes. |
| PG075 | 52 | `formatter-linter-normalizer` | Produce clean and deterministic source and configuration before build execution. |
| PG076 | 52 | `generation-manifest-and-sbom` | Create the authoritative handoff from generation to build, test, security, and delivery. |