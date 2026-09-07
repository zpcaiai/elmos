# Polyglot Repository Translator roadmap

## Architecture

```text
Java | Python | C# | JavaScript/TypeScript adapters
                       |
                       v
             Unified Intermediate Representation
                       |
                       v
Java | Python | C# | JavaScript/TypeScript generators
                       |
                       v
       framework recipes -> agent repair -> verification gates
```

The architecture avoids twelve unrelated source-to-target pipelines. Deterministic parsers/recipes own repeatable transformations; agents operate only on evidenced long-tail failures and cannot override gates.

## Batches

1. **Repository Intake** — immutable snapshot, fingerprint, Build Model, inventory, dependency graph, sandbox policy, source baseline and frozen manifest. Implemented in `modules/intake`; a real baseline still requires the approved Workspace runner.
2. **Semantic adapters** — PSP v1 orchestration, lossless syntax/trivia, authority-bound Java, Python, C# and JavaScript/TypeScript adapters, symbols/types/graphs/diagnostics, per-module gates, Zstandard streams and SQLite index are implemented in `modules/semantic`. Native analyzer workers remain deployment capabilities; syntax fallback is deliberately blocking.
3. **UIR** — implemented in `modules/uir`: dialect registry, deterministic PSP lifting, declarations/types/operations, linked structured and CFG/SSA views, effects, exceptions, async, aliases, opaque semantics, obligations, provenance, gates, streams and index.
4. **Target skeletons** — implemented in `modules/skeleton`: target profile/stack/module/naming/build planning, four-language deterministic contract skeletons, protected placeholders, mappings, external baseline evidence and S-A through S-D gates.
5. **Core language translation** — implemented in `modules/lowering`: faithful-first callable planning, target-version capability/rule governance, type/evaluation/effect-aware operation plans, injected AST/compiler backends, optional verified idiomatization, protected callable patches, bounded agent packets, artifacts and L-A through L-D module gates. Native language emitter/compiler workers remain deployment capabilities; missing backends fail closed.
6. **Library/dependency mapping** — implemented in `modules/dependency-migration`: normalized and resolved graphs, actual API-use and semantic profiles, provenance-bearing candidates, non-compensating compatibility/supply-chain gates, adapters/compatibility runtimes/wrappers/sidecars/retained runtimes, declarative build patches, differential validation and D-A through D-D.
7. **Framework recipes** — implemented as an evidence-bound AFSM control plane in `modules/framework-migration`: multi-evidence fingerprinting, authority-bound lifting, deterministic recipes, native emitter/startup ports, semantic diffs and F-A through F-D gates across REST, DI, validation, ORM, transactions, security, config, messaging, cache, scheduling and lifecycle. Native source/target framework workers remain deployment capabilities.
8. **Build/test repair loop and repository-aware agents** — implemented in `modules/repair-orchestration`: polyglot matrices, isolated execution ports, Diagnostic normalization/clustering/attribution, deterministic-first bounded Agent patches, transactional apply/rollback, test migration, flaky governance, regression, budgets, finite stopping, evidence artifacts and R-A through R-D.
9. **Behavioral equivalence** — implemented in `modules/behavior-equivalence`: fixed source/target Snapshots, isolated dual runtimes, aligned state/time/random/external responses, OBM observations, reviewed canonicalization/Golden/tolerance/approved-change governance, multi-Oracle HTTP/data/transaction/message/file/cache/error/audit/concurrency comparisons, property/metamorphic validation, flaky detection, Batch 8 feedback, immutable evidence and E-A through E-E.
10. **Production hardening** — implemented in `modules/production-hardening`: immutable artifact admission, per-service risk profiles, sanitized production workload models, calibrated load/tail-latency/resource/capacity/soak evidence, supply-chain/application/identity/tenant/data security, bounded chaos/crash/restore/PITR/DR, telemetry/SLI/SLO/alert/runbook validation, signed release provenance, canary/rollback/cost evidence, append-only packs and P-A through P-F gates.
11. **Progressive production cutover and closure** — implemented in `modules/production-cutover`: P0 through P12 PCCM, wave/cohort routing, Expand–Migrate–Contract, inventory/mapping, resumable backfill, CDC/final delta, single write authority, shadow/read/write canaries, integration closure, rollback/forward-fix, Hypercare, five-dimension acceptance, retirement, append-only acceptance packs and C-A through C-G gates.
12. **Enterprise multi-tenant migration platform** — implemented in `modules/enterprise-platform`: immutable Batch 1–11 platform admission, tenant/isolation profiles, federated identity and policy evidence, private Runner, model/cost, data governance, five independent deployment modes, append-only evidence and T-A through T-G gates. It reuses the existing runtime authorities and never executes customer code or production operations.
13. **Enterprise commercial loop** — implemented in `modules/commercial-loop`: EMCOM covers eight business domains and six commercial motions, consumes seven external authority envelopes, preserves normal/exception lifecycles, produces append-only commercial artifacts, and adjudicates B13-A through B13-G without executing CRM, finance, customer, partner or production operations.
14. **Product and ecosystem growth** — implemented in `modules/ecosystem-growth`: PEGM Monthly Verified Migration Value, seven value domains, five measured flywheels, complete Skills 401–460, append-only evidence and G14-A through G14-G without executing external growth or ecosystem operations.
15. **Company operating and governance system** — implemented in `modules/company-series`: COGS, eight operating domains, complete Skills 461–525 and sequential C15-A through C15-G without executing company, finance, HR, legal or board actions.
16. **AI-native company and Agent Workforce** — implemented in `modules/company-series`: A0–A6 autonomy, Human Owner and authority envelopes, evaluation/Shadow/security/rollback controls, complete Skills 526–592 and AI16-A through AI16-G; unbounded autonomy is prohibited.
17. **Vertical solution factory** — implemented in `modules/company-series`: shared core plus industry, jurisdiction and customer-extension layers, seven verticals, complete Skills 593–668 and V17-A through V17-G without making compliance or production-readiness claims.
18. **Group integration factory** — implemented in `modules/company-series`: GITM, Day 1/100, portfolio, identity/data, Wave, TSA, carve-out, synergy and retirement controls, complete Skills 669–745 and M18-A through M18-H without executing transaction or production integration actions.
19. **Software delivery and platform engineering** — implemented in `engines/software-delivery-platform-engine`: SCM, value stream, pipeline components, artifacts, environments, IDP, Golden Paths, self-service, DORA and platform-product evidence without production administration.
20. **AI/ML and generative AI platform** — implemented in `engines/ai-platform-engine`: data/features, reproducible training, registry, serving, LLM gateway, RAG, Agents, evaluation, guardrails, Responsible AI and AI FinOps with independent release gates.
21. **Edge, IoT and industrial systems** — implemented in `engines/edge-iot-industrial-engine`: passive estate, industrial semantics, OPC UA, MQTT/Sparkplug, Edge runtime, identity, OTA, Twin, historian, Edge AI and SIL/HIL behind an outbound site Runner.
22. **Operations, SRE and ITSM** — implemented in `engines/operations-sre-itsm-engine`: service topology, events, Incident, problem, Change, SLO, Runbook, bounded remediation, capacity and continuity with business verification.
23. **Enterprise architecture and application portfolio** — implemented in `engines/enterprise-architecture-engine`: context/capability, evidence graph, application/technology portfolios, options, investments, ADRs, roadmaps and conformance without automatic decisions.

## Batch 1 gate

Batch 2 may start only when the source identity, detected projects/builds, inventory, build dependency graph, sandbox policy and baseline are all recorded under the same snapshot. Existing source tests may fail, but their names and evidence must be preserved. Batch 1 never emits target-language code.

## Batch 2 gate

Batch 3 may lift only modules that pass PSP schema, referential/source integrity, and module-level Gate A without blocking diagnostics. Missing language authority, unresolved provenance, dangling IDs, or a changed source hash fails closed. Batch 2 never emits a target repository or target-language source.

## Batch 5 gate

Batch 5 lowers only callables whose UIR module and Batch 4 skeleton module are eligible and whose Target Declaration ID still resolves to an unchanged generated region. Faithful output must pass the configured target parser, symbol and type backend before any idiomatic rewrite or patch. Missing compiler/AST backends, opaque semantics, public lossy types, rule conflicts, changed manual regions or open blocking obligations prevent promotion. L-C/L-D means ready for dependency/framework work, not behavioral equivalence.

## Batch 6 gate

Batch 6 operates only on target modules admitted by Batch 5. D-A requires a normalized, exact and evidence-backed dependency graph. D-B requires complete used/unused/unknown classification, semantic profiles and an explicit strategy per dependency. D-C additionally requires target policy, license/security/platform/support and sandboxed native build resolution with regenerated locks and disabled lifecycle scripts. D-D requires complete API-contract and differential obligations, including boundaries and lifecycle. Missing catalog, supply-chain, resolver or validation authority fails closed; package-name similarity and aggregate scores cannot override blockers.

## Batch 7 gate

Batch 7 operates only on modules admitted by Batch 6 D-D. F-A requires a complete, provenance-bearing AFSM lift and deterministic recipe for every framework entity. F-B additionally requires a safe isolated bootstrap, DI/container resolution, route discovery and OpenAPI generation. F-C requires complete endpoint, validation, transaction, authentication and authorization strategies with no open blocking obligation. F-D adds strict messaging/cache/scheduler fidelity, smoke/shutdown evidence, trace coverage and reviewed high-risk Agent output. Startup success, generated syntax or a green health endpoint does not establish behavioral or production equivalence.

## Batch 8 gate

Batch 8 operates only on Batch 7-admitted target Snapshots with a comparable source baseline. R-A requires reproducible dependency restore/build-model load and a controlled compile baseline. R-B requires symbol/type/static stability with no critical finding or public-API regression. R-C requires complete discovery, explicit source-test states, required test thresholds and no unclassified failure. R-D adds full compile/regression, zero required migration/security regression, no open blocking obligation, reviewed high-risk Agent patches and matching clean-environment runs. Incremental success, retry-then-pass, deleted/weakened tests or a passing build cannot establish R-D.

## Batch 9 gate

Batch 9 operates only on Batch 8 R-D modules bound to immutable source/target Snapshots. E-A requires isolated mutable resources, aligned configuration/state/time/random/external responses and complete critical observation points. E-B adds complete critical HTTP and public contract equivalence. E-C adds strict database, transaction, message, file and audit effects. E-D requires every critical scenario, at least 0.98 required-scenario acceptance, zero critical unknown/open blocking obligation/unapproved high-risk change/flaky difference, strict security-money-transaction behavior and at least two matching clean runs. E-E raises required, observation and trace coverage to at least 0.995 and requires property/metamorphic rates of at least 0.99. HTTP equality, a reviewed ordinary approved change or a repository average cannot hide one failed side effect or module. E-D/E-E admit only to Batch 10 production hardening and never authorize cutover.

## Batch 10 gate

Batch 10 admits only an immutable Batch 8/9-passed artifact and evaluates every deployable service independently. P-A requires calibrated normal/peak/stress and risk-required soak, passing p95/p99/error objectives, overload recovery and headroom. P-B adds zero blocking supply-chain, code, API, secret, identity, tenant, crypto and configuration findings. P-C adds bounded failure behavior, no corruption and required crash/restore/PITR/DR evidence. P-D adds calculable SLI/SLOs, correlated telemetry, tested alerts and validated runbooks. P-E adds signed immutable provenance, reproducibility, cost, canary and rollback controls. P-F requires high-confidence critical coverage, headroom and zero open risks. P-E/P-F mean only eligibility for progressive delivery: Batch 10 always keeps production readiness and cutover false, and never performs production deployment or destructive production chaos.

## Batch 11 gate

Batch 11 admits only the same immutable target artifact at Batch 10 P-E/P-F with progressive-delivery eligibility. C-A requires complete production topology, safe Expand–Migrate–Contract, authoritative inventory/mapping, an approved resumable/idempotent backfill and healthy full-operation CDC. C-B adds verified backfill, bounded lag, per-asset reconciliation, isolated shadow reads and zero critical read differences. C-C requires target reads at 100%, stable cohorts, one atomic write-authority registry, no dual primary, all entry points compliant and validated rollback/stop triggers. C-D adds a stable write canary, final freeze/drain/delta closure, equal positions, reconciliation and integration fidelity. C-E requires target writes at 100%, target truth, source writes at zero and a verified rollback or approved irreversibility path. C-F requires completed Hypercare, continuous SLO/data/business evidence, five-dimension acceptance, operations handoff, full legacy drain and verified archive/restore/legal hold. Only C-G at observed P12 can mark migration complete, and it additionally requires external decommission evidence, credential/DNS/infrastructure/license closure, complete traceability and zero critical risk. The control plane never performs these production operations; absent authority evidence remains `NOT_RUN` or blocked.

## Batch 12 gate

Batch 12 admits only an immutable, signed platform artifact bound to the Batch 1–11 control planes. T-A validates tenant ownership/isolation and federated identity; T-B authorization, approvals and tamper-evident audit; T-C private Runner identity, sandbox, egress and secret boundaries; T-D Model Gateway, quota, immutable metering and billing; T-E residency, retention, Legal Hold, deletion and key governance; T-F all five deployment modes independently; T-G HA/DR, operator surfaces, four-party acceptance, contractual alignment, traceability and zero Critical risk. A mode cannot borrow evidence from another. Only T-G may set enterprise delivery readiness, while the evaluator always keeps production operation execution false. Real integrations and deployment drills remain `NOT_RUN` until external authorities evidence the exact platform version.

## Batch 13 gate

Batch 13 admits only an immutable, signed Batch 12 artifact with externally verified T-G provenance. B13-A requires complete discovery and objective, failure-preserving POC evidence; B13-B aligns catalog, pricing, quote, SOW, contract, approvals, margin, security and entitlements; B13-C validates safe onboarding, owned baselines, scope control, delivery evidence, acceptance and billing authorization; B13-D validates supportability, P1 escalation, health, value, renewal and churn action; B13-E validates partner diligence, certification, isolation, quality and settlement; B13-F validates authoritative metrics, forecast, capacity, cost, margin and owned risk; B13-G requires all six motions accepted, full traceability, aligned contractual capabilities and zero critical commercial risk. Only B13-G may set commercial-scale candidacy. The evaluator never performs an external commercial operation, and missing field evidence remains `NOT_RUN`.

## Batch 14 gate

Batch 14 admits only an immutable, signed Batch 13 artifact with externally verified B13-G provenance, a value-bound and versioned Monthly Verified Migration Value definition, all seven PEGM domains and all five guarded flywheels. G14-A validates self-service activation, TTV, Trial cost and security; G14-B validates reviewed content plus developer portal/docs/SDK/sample journeys; G14-C validates isolated and safely moderated community knowledge; G14-D validates publisher, asset security/License, installation rollback and review trust; G14-E validates I18n, human-reviewed critical localization, regional formats and compliance; G14-F validates entry assessment, Launch Playbook, support, partner quality and regional metrics; G14-G requires all six prior gates, complete traceability, visible channel CAC and contribution margin, all six supported growth motions and zero critical open growth risk. Only G14-G may set `scalable-growth-ready`. The evaluator never executes an external identity, messaging, publishing, Marketplace, payment, moderation, legal or regional operation; missing field evidence remains `NOT_RUN`.
