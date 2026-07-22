---
name: mainframe-target-profile-and-modernization-planner
description: Select evidence-based modernization paths per mainframe application, business capability, online transaction, batch job, and data domain. Use to compare keep/optimize, API enablement, COBOL modularization, hybrid extraction, language transformation, replatforming, package replacement, data-only modernization, and retirement.
---

# Mainframe Target Planning

## Plan per capability

1. Assess criticality, volume, batch window, data gravity, dynamic calls, copybook stability, subsystem coupling, test readiness, latency, availability, skills, cost, and regulation.
2. Evaluate `KEEP_AND_OPTIMIZE`, `API_ENABLE`, `MODULARIZE_COBOL`, `HYBRID_EXTRACT`, `COBOL_TO_JAVA`, `REPLATFORM_RUNTIME`, `DATA_ONLY_MODERNIZATION`, `PACKAGE_REPLACEMENT`, and `RETIRE` without a migration-out bias.
3. Plan online transactions, batch workloads, data ownership, and terminal journeys separately while preserving shared rules and contracts.
4. Prefer facade, consumer migration, dual run, controlled traffic shift, and reversible removal for strangler paths.
5. Require input snapshots, shadow execution, output comparison, scheduler canary, and legacy standby for batch paths.

## Gate the plan

- Do not select language transformation for unresolved dynamic calls, assembler interfaces, unknown copybooks, IMS-position dependencies, uncontrolled transactions, production side effects, or weak test baselines.
- Emit an explicit blocked plan when no safe path exists.
