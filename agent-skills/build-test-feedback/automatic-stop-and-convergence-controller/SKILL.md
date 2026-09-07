---
name: automatic-stop-and-convergence-controller
description: "Choose Batch 8 continue, success, partial, environment, budget, oscillation, risk, human, or safe-failure outcomes. Use after every validation round and before closing a repair run."
---
# Automatic Stop and Convergence Controller
Read `../references/batch-8-repair-loop.md` and emit `contracts/repair-loop-schema/stop-decision.schema.json`.

Require restore, build-model load, full compile, no blocking static/security/migration regressions, complete required discovery/execution, no open blocker, reviewed high-risk patches and matching clean runs for success. Preserve the stable Snapshot.

Stop immediately on production access, secret leak, data/security risk, scope breach, unreviewed contract drift or failed rollback. Never use build-pass alone, flaky retries or waived obligations as convergence.
