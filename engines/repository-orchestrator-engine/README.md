# ELMOS Repository Orchestrator Engine

This repository-owned Python runtime implements deterministic, provider-free
semantics for the 54 exact Skills in
`elmos-repository-task-decomposition-cost-router-skills` v2.0.0.

The source ZIP is declarative, untrusted input. The integration tooling reads
it without importing or executing package code. The runtime performs bounded
planning, graph validation, model selection, cost/ETA estimation, evidence
classification, and fail-closed gate decisions. It does not invoke models,
create worktrees, apply patches, deploy, or certify a repository.

Invoke one exact Skill with JSON on stdin:

```bash
PYTHONPATH=engines/repository-orchestrator-engine/src \
  python -m elmos_repository_orchestrator.cli invoke \
  elmos-task-granularity-controller --scope-json scope.json < request.json
```

Run all package checks with:

```bash
make repository-orchestrator-skills
```
