# Elmos Skills Package Runtime Instructions

When implementing a medium/large repository requirement, start with `skills/00-repository-orchestrator/SKILL.md`.

Rules:
1. Resolve the run through `skills/36-model-selection-controller/SKILL.md`: Smart routes per task; Manual pins primary implementation to the user-selected model and obeys its fallback/verification policy.
2. Treat `config/model-registry.yaml` as a hard allowlist. Never introduce or invoke any model alias outside the ten listed aliases.
3. Decompose before coding. A worker must receive one validated atomic task, owned/read/forbidden paths, acceptance commands and a context pack.
4. Use isolated git worktrees/branches for workers. Never let parallel workers write the same owned path.
5. Run deterministic validators before model review or escalation.
6. Retry at most according to `config/router-policy.yaml`; escalate failure classes rather than repeatedly calling a cheap model.
7. Preserve `.elmos/runs/<run_id>/` state so the job can resume after interruption.
8. Final completion requires `skills/31-repository-certifier/SKILL.md` and original requirement acceptance scenarios.
9. Report autonomous machine wall-clock runtime, cost/credit usage, retries, model distribution and remaining risks.

Recommended run artifacts:
```
.elmos/runs/<run_id>/
  manifest.json
  model-selection.json
  requirement.json
  repo-profile.json
  architecture-index.json
  impact-map.json
  dag.json
  tasks/<task_id>.json
  contexts/<task_id>/manifest.json
  executions/<task_id>/<attempt>.json
  evidence/<task_id>/...
  integration-log.jsonl
  events.jsonl
  state.json
  certification.json
```
