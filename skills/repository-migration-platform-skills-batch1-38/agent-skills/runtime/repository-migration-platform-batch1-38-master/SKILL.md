---
name: repository-migration-platform-batch1-38-master
description: >-
  Orchestrate Batch 1–38 as one evidence-governed repository modernization and final system assurance program. Use when orchestrating the complete Batch 1-38 repository migration lifecycle, executing all Batch work units, or evaluating final assurance.
---

# Repository Migration Platform Batch 1–38 Master

## Contract Metadata

- Version: `2.0.0`
- Batch: `master`
- Risk: `critical`
- Gate: `SA1–SA5 final orchestration`


## Objective

Execute the complete lifecycle from immutable Source discovery through semantic migration, complete project generation, production cutover, business/data/admin closure and SA1–SA5 final assurance.

## Required Inputs

- Source repository or immutable snapshot;
- Business scope, critical journeys, data and security constraints;
- Target objectives, team, budget and migration window;
- Required certification levels and production environments.

## Workflow

1. Execute Batch 1–3 to freeze and understand Source;
2. Execute Batch 4–11 to lower languages, frameworks, infrastructure and domains;
3. Execute Batch 12–15 to migrate, prove and repair;
4. Execute Batch 16–20 to plan, run, generate and productize;
5. Execute Batch 21–28 to close capability, business, data, admin, identity and usability;
6. Execute Batch 29–34 to close regression, resilience, transactions, performance, security and providers;
7. Execute Batch 35–38 to accept production, operate, retire Source and issue final assurance.

## Non-Negotiable Gates

- No Build-success-as-equivalence;
- No Test-pass-as-proof;
- No Builder self-verification or self-certification;
- No hidden failed attempts, mutation survivors, fuzz crashes or incidents;
- No permission expansion, cross-tenant access, money imbalance, unsafe device action or duplicate irreversible effect;
- No Source retirement before hidden caller, credential, data and provider closure.

## Verification

Run `./validate.sh`, then execute each Batch Gate in dependency order. The package validator checks package structure only; runtime and production claims require real project Evidence.

## Stop and Escalate

Stop on unknown critical scope, broken lineage, invalid certificates, unsafe side effects, irreversible migrations without recovery, or unresolved critical business/data/security findings.


## Executable Runtime

1. Resolve the shared runtime installed by `install.sh`, or use the package-local `scripts/migration_platform.py`.
2. Prepare all work units without claiming completion:

   ```bash
   python3 "$RMP_RUNTIME" prepare-all --source "$SOURCE_REPO" --workspace "$EVIDENCE_WORKSPACE" --target-objective "$TARGET_OBJECTIVE"
   ```

3. Fill each generated `execution-plan.json` with exact argv-only steps and run it with `execute-plan`; import separately produced subject bytes with `ingest-artifact` before recording typed Evidence.
4. Record and independently verify the exact output/test evidence requested by each Batch profile.
5. Evaluate every local gate in dependency order:

   ```bash
   python3 "$RMP_RUNTIME" gate-all --workspace "$EVIDENCE_WORKSPACE" --mode local
   ```

6. Treat `LOCAL_TOOLKIT_PASS` as the absolute local ceiling. The distributed trust policy disables certificate requests/imports; production or certification states remain `NOT_RUN` until an independently governed distribution supplies a pinned trust root.
## Definition of Done

All 38 Batch reports are present, all applicable gates pass, the final target owns the declared production scope, Source retirement is evidenced, and SA1–SA5 status is computed conservatively.
