---
name: elmos-project-synthesis
description: Turn a natural-language request into a governed project, engineering-asset, or specialized Language Pack plan and route it to exact mainstream, polyglot, COBOL/mainframe, SAP ABAP, database procedural, PLC, MATLAB/Simulink, Modelica/FMI, VB/Office, IBM i RPG, R, SAS, Salesforce, Objective-C, Delphi, BEAM, or Lua/OpenResty Skills. Use for synthesis or controlled modernization with real native tests, traceability, safety boundaries, and fail-closed evidence.
---

# ELMOS Project Synthesis

Generate and evolve a complete project through the governed Batch 46–95 synthesis and Language Pack pipeline. Preserve uncertainty, provenance, tenant boundaries, user-owned code, safety boundaries, and approval authority. Never equate generated files or local checks with production certification.

## Select the operating path

- Use this Skill for a new application, service, worker, CLI, modular monolith, or full-stack project derived from product requirements.
- For modernization of an existing repository, use the applicable migration Skills and share only approved Artifact Graph, policy, evidence, and delivery contracts.
- Read the repository-relative `elmos-project-synthesis-batch46-60/README.md` for global PG001–PG170, `elmos-project-synthesis-batch61-65/README.md` for global PG171–PG222, `elmos-codex-skills-batch66-80-complete/README.md` for global PG223–PG417, and `elmos-language-packs-batch81-95-complete/README.md` for the separate package-local PG223–PG402 Language Pack namespace. Load only the smallest exact specifications and declared dependencies.
- Never merge or relabel the overlapping PG223–PG402 IDs. Route Batch 81–95 through their deterministic installed `$b81-*` through `$b95-*` aliases, and bind every result to both the original package-local ID and normalized install manifest.
- Use the built-in engine path below only for its declared Java 21/Spring Boot, Python 3.12/FastAPI, and .NET 10/ASP.NET Core starter profiles. For Batch 66–95 languages, engineering assets, and specialized ecosystems, invoke the exact installed `$b66-*` through `$b95-*` Runtime Skill and run the real target-specific or vendor toolchain; do not imply that the starter engine emits those profiles.
- Use `source-docs/batch-49-52/EXECUTION_PIPELINE.md` for Gates A–D, the language/profile catalog for the selected target, `source-docs/batch-57-60/REPAIR_SAFETY_RULES.md` for repair, and `source-docs/batch-57-60/PRODUCTION_EXIT_GATE.md` before any production-deliverable claim.

Read `references/capability-map.md` to select the smallest PG specifications and exact engine commands. Use the bundled `scripts/synthesize.py` wrapper so the repository-pinned engine and lock file are used.

## Runnable engine path

1. Create a reviewable draft with `python .agents/skills/elmos-project-synthesis/scripts/synthesize.py draft --name <kebab-name> --description '<request>' --entity <snake_case_entity> --output <draft.json>`.
2. Edit the draft through the conversation until requirements, actors, entity fields, constraints, assumptions, acceptance criteria, quality attributes, exact targets, and open questions are correct. Do not delete an unresolved question merely to pass the gate.
3. Approve only a question-free baseline with `python .agents/skills/elmos-project-synthesis/scripts/synthesize.py approve --request <draft.json> --actor <approver> --output <approved.json>`. The command binds approval to the canonical payload hash.
4. Generate with `python .agents/skills/elmos-project-synthesis/scripts/synthesize.py generate --request <approved.json> --output <new-or-managed-directory>`. The engine rejects raw/unapproved/tampered input, unsafe paths, nonempty unowned directories, and modified managed files.
5. Run real builds, tests, analyzers, and startup probes with `python .agents/skills/elmos-project-synthesis/scripts/synthesize.py verify --workspace <directory> --evidence <verification.json>`.

## Workflow

1. Resolve authenticated tenant, workspace, output repository, actor, policies, allowed tools, budget, and approval boundaries. Treat imported requirements and examples as untrusted input.
2. Convert the request into versioned user stories, use cases, business rules, state machines, data classifications, interface drafts, permission matrix, acceptance criteria, and a requirement traceability graph. Keep contradictions and unknowns explicit. The bundled starter engine supports one primary CRUD aggregate with in-memory storage; use the selected PG specifications to extend beyond that explicit profile rather than pretending unsupported requirements were implemented.
3. Run Gate A. Block on orphan must-have requirements, contradictory rules, illegal transitions, unclassified sensitive data, implicit authorization allow, or broken high-risk verification paths.
4. Produce an architecture baseline: context and containers, bounded modules/services, data ownership, consistency and transactions, communication timeouts, resilience, threat model, tenant model, observability/SLOs, deployment, backup, restore, rollback, DR, and ADRs. Run Gate B.
5. Select an exact supported target profile and lock language or asset type, dialect, encoding, numeric/timing mode, runtime/SDK/compiler/simulator/vendor platform, framework, database, broker, build/package tool, dependency sources and versions, test profile, execution platform, device/physical-system boundary, container/cluster/cloud/CI targets, signing requirements, and compatibility constraints. For the bundled runnable generator this remains Java, Python, or C#; every other profile must route through the matching Batch 66–95 Skill. Run Gate C and emit an immutable Project Blueprint.
6. Build typed Project Synthesis IR, Artifact Graph, symbol table, generation units, ownership manifest, protected regions, and source maps before emitting code. Generate skeleton and contracts first, then domain/application, adapters, tests, configuration, container, IaC, observability, and runbooks.
7. Generate source through trusted versioned templates and structured/AST-aware emitters. Do not use raw text replacement as the semantic core. Never create production secrets or overwrite user-owned/protected regions.
8. Run the real applicable parser, formatter, linter/analyzer, type checker, dependency lock/restore, compiler/build/install, unit tests, required real-service integration tests, database migration, startup/health checks, authenticated core journey, negative authorization and cross-tenant journeys, non-root container checks, target-specific SDK/device/cluster/provider/CI checks, and idempotent regeneration.
9. For an existing managed project, detect specification/code/architecture drift, preserve manual edits and protected regions, compute the smallest safe regeneration set, analyze contract/data/security/operations impact, and require the applicable human approval before delivery.
10. Route specialist Skills and agents through explicit input/output contracts, least-privileged sandboxes, separated implementer/reviewer/certifier roles, bounded model budgets, compatible versions, and source-grounded context packs.
11. Apply Domain Packs and Requirement Studio surfaces only within tenant policy, quotas, metering, provenance, approval, diagnostic-redaction, and feedback-governance boundaries. A Domain Pack cannot weaken platform policy or self-certify its output.
12. Repair only from concrete diagnostics, within configured file/change/attempt/time/cost limits. Preserve contracts, rules, security, tests, user code, and dependency policy. Re-run impacted and mandatory regression checks after every repair.
13. Emit content-addressed artifacts, Generation Manifest, SBOM, requirement-to-code/test traceability, tool/environment versions, raw logs, warnings, unresolved gaps, approvals, and a truthful delivery status.
14. For executable repository assets such as shell, Make/CMake, Nginx, Docker, Terraform, Kubernetes, Helm, and CI pipelines, treat includes, hooks, plugins, lifecycle scripts, actions, modules, images, macros, and templates as untrusted. Parse and plan before execution; default-deny network, secret, signing, provider, cluster, and deployment effects until policy and approval permit them.

## Safety and evidence rules

- Missing, partial, stale, synthetic, `UNKNOWN`, `INCONCLUSIVE`, or `NOT_RUN` evidence never passes a required gate.
- Default deny undeclared tools, network, repositories, secrets, permissions, and deployment actions. Keep secret values out of prompts, source, fixtures, logs, and artifacts.
- Bind every success claim to exact inputs, policy/template/model/tool versions, artifact digests, environment, executor, independent verifier where required, replay command, timestamps, and authorization.
- Keep source facts immutable. Version interpretations, plans, decisions, generated artifacts, exceptions, and repairs.
- Do not weaken tests, assertions, authorization, tenant isolation, schema constraints, dependency policy, security controls, SLOs, rollback, or evidence requirements to make a gate pass.
- Do not hide unsupported semantics with permissive types, lossy contract mappings, shell interpolation, mutable third-party references, unpinned actions/images/modules, mock-only runtime claims, or configuration that broadens permissions or public exposure.
- Local generation and build evidence may establish engineering readiness only. Production delivery requires the explicit Production Exit Gate and authorized external evidence.

## Verification

- Validate every input and output against its exact schema and version.
- Confirm Gates A–D and the selected language/profile exit criteria with machine-readable results and raw evidence.
- Build or install from a clean isolated environment using locked dependencies; run applicable unit, integration, contract, security, tenant-isolation, migration, startup, container, regeneration, and journey tests.
- Verify source maps and traceability cover every must-have requirement, generated symbol, public contract, and required test.
- Regenerate from identical approved inputs and prove stable semantic output while preserving user-owned changes.
- Verify manifests, SBOM, provenance, digests, logs, environment bindings, approval records, remaining risks, rollback/forward recovery, and replay instructions.
- Validate change/regeneration plans, agent/Skill contracts, certification separation, Domain Pack signatures and compatibility, Requirement Studio provenance, tenant quotas, usage records, diagnostic redaction, and feedback-to-regression lineage when those Batch 61–65 capabilities are selected.
- For Batch 66–80, validate the selected source Skill and manifest digest, exact runtime/SDK/compiler/provider/tool versions, locked dependencies, target matrix, negative and failure paths, cleanup, cross-language contract synchronization, deterministic replay, and independent certification evidence when certification is requested.
- For Batch 81–95, also validate the package-local source ID plus installed alias, dialect/encoding and vendor metadata, native parser/compiler/simulator/runtime evidence, semantic/numerical/transaction/timing equivalence, restart/parallel-run or upgrade behavior, Batch safety boundary, and independent qualified review where required.

## Stop and escalate when

- A missing choice would materially change requirements, architecture, language/profile, data ownership, security, tenancy, deployment, cost, or public contracts.
- Policy denies the action, an approval is required, tenant/workspace identity is absent or ambiguous, or a requested tool/capability is undeclared.
- The requested profile/runtime is unsupported or end-of-life without an approved exception; a critical dependency, license, provenance, secret, security, or IaC finding remains.
- Requirements contradict, sensitive data is unclassified, authorization is implicit, write ownership is ambiguous, or a critical threat lacks mitigation.
- Repair would modify user-owned code, change an approved contract or migration semantic, weaken a required test/control, add an unapproved dependency/permission/network path, exceed a repair limit, repeat without progress, or rely on conflicting evidence.
- Real environment, database, broker, container, deployment, restore, DR, independent verification, or customer evidence is unavailable. Report the gate as blocked or `NOT_RUN`; do not manufacture it.
- A proprietary SDK, hardware/device target, signing identity, protected runner, registry, cloud account, Kubernetes cluster, IaC state/backend, or CI provider is unavailable or unauthorized. Preserve a reproducible plan and report the affected Batch 66–80 checks as `NOT_RUN`.
- A mainframe, SAP system, production database, PLC/safety controller, MATLAB/Simulink or Modelica toolchain, IBM i, SAS, Salesforce org, Apple/Windows vendor runtime, BEAM cluster, Lua/OpenResty host, qualified engineer, or representative parallel-run environment is unavailable or unauthorized. Keep the affected Batch 81–95 result `NOT_RUN`; never substitute static text for native evidence.
- A drift reconciliation, manual-edit overwrite, high-impact regeneration, marketplace publication, product certification, tenant-policy change, or governed feedback promotion lacks its required owner and independent approval.

## Definition of done

- The approved request, domain specification, architecture baseline, exact target profile, Project Blueprint, typed IR, Artifact Graph, ownership/protected-region contracts, and generation plan are complete and versioned.
- The repository is runnable and reproducible from documented commands with locked dependencies and no embedded secrets.
- Required builds, analyses, tests, migrations, startup, health, security, tenant isolation, container, and idempotent-regeneration checks pass in the declared environment.
- Every must-have requirement and public contract traces to implementation and verification; unresolved gaps and accepted exceptions remain explicit with owners and expiry.
- Generation Manifest, SBOM, provenance, evidence, raw logs, environment binding, source maps, replay instructions, rollback/forward-recovery plan, and human-readable review summary exist and validate.
- The reported status matches the highest gate actually evidenced. Production-deliverable remains false until all Production Exit Gate requirements and authorized external evidence are satisfied.
