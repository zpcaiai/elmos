---
name: elmos-proof-driven-harness-intelligence
description: Repository-scale proof-driven Agentic Harness for Elmos. Use for project generation, modernization, cross-language conversion, SQL migration, repository refactoring, multi-agent execution, verification, recovery, certification, and skill evolution.
version: 1.0.0
priority: P0
---

# Elmos Proof-Driven Harness Intelligence

<system-conventions>
RFC 2119 applies to MUST, REQUIRED, SHOULD, RECOMMENDED, MAY, OPTIONAL.
NEVER = MUST NOT. AVOID = SHOULD NOT.
</system-conventions>

<stakes>
This skill governs production changes to real repositories. Incorrect semantic assumptions can create silent behavioral regressions, security defects, data corruption, invalid migrations, or non-recoverable long-running jobs.
</stakes>

<critical>
- MUST treat LLM output as a hypothesis until verified.
- MUST prefer the highest available authority: formal proof > compiler > LSP > Semantic IR > AST > runtime > text > LLM.
- MUST model every repository mutation as a PatchTransaction with preconditions, postconditions, evidence, and rollback.
- MUST use strict typed outputs for transformation, verification, merge, certification, and production-control tasks.
- MUST isolate concurrent write-capable agents by owned workspace/revision/lease/fence.
- MUST attach evidence provenance to every pass/fail claim.
- MUST use an independent assurance path for release-affecting verification.
- MUST NOT silently downgrade a failed semantic check to text inference.
- MUST NOT silently shadow policy conflicts; conflicts require explicit resolution records.
- MUST persist durable progress before externally visible side effects.
- MUST make pause/resume/cancel/retry/replay idempotent.
- MUST record machine wall-clock execution time, cost, tokens, retries, and verification outcomes.
</critical>

## Trigger

Load this skill for any task that modifies or certifies a repository at project scale, especially:

- legacy modernization;
- cross-language conversion;
- project generation;
- SQL migration;
- large refactoring;
- parallel multi-agent coding;
- production certification;
- long-running repository jobs;
- automated repair loops.

## Mandatory execution workflow

1. **Intake** → resolve repository, revision, business route, constraints, certification target.
2. **Preflight** → detect build systems, languages, frameworks, LSP/compiler/runtime availability, security boundaries.
3. **Semantic prewalk** → build RepositorySemanticGraph before broad mutation.
4. **Plan DAG** → partition work by semantic dependency and write scope.
5. **Allocate** → bind each agent to model role, tools, workspace, lease, fence, budget, invariants.
6. **Transform** → execute semantic/AST/IR-first PatchTransactions.
7. **Verify locally** → compiler/LSP/tests/runtime checks after each bounded transaction.
8. **Integrate** → merge only verified outputs; detect semantic and patch conflicts.
9. **Independent assure** → advisor/watchdog/reviewer evaluates evidence, not executor confidence.
10. **Certify** → assemble E0–E5 CertificationBundle.
11. **Learn** → successful repairs become skill candidates only after regression and corpus validation.
12. **Release/rollback** → release only at required gate; otherwise persist residual risk and rollback path.

## Kernel loading

Load only the kernels required for the current phase:

- `10-semantic-intelligence/SKILL.md`
- `20-transactional-transformation/SKILL.md`
- `30-runtime-proof/SKILL.md`
- `40-agentic-execution/SKILL.md`
- `50-independent-assurance/SKILL.md`
- `60-policy-invariants/SKILL.md`
- `70-skill-evolution/SKILL.md`
- `80-harness-intelligence/SKILL.md`
- `90-production-control-plane/SKILL.md`
- `95-certification/SKILL.md`

## Done definition

A repository job is NOT done when code generation stops. Done requires:

- expected artifacts exist;
- semantic integrity checks pass;
- repository builds where applicable;
- required tests pass;
- runtime equivalence evidence exists where migration behavior matters;
- unresolved P0/P1 findings are zero unless a formal exception is approved;
- certification target is satisfied;
- rollback/recovery metadata is durable;
- execution metrics are recorded;
- skill-learning candidates are quarantined from production until certified.
