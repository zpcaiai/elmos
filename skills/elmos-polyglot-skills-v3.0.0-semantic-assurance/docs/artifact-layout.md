# Recommended Runtime Artifact Layout

```text
.elmos/
  runs/<run-id>/
    run.json
    policy/
    snapshot/
    discovery/
    contracts/
    ir/
    target/
    plan/
    worktrees/
    patches/
    builds/
    tests/
    validation/
    evidence/
    readiness/
    delivery/
    checkpoints/
    logs/
```

Large artifacts should live in content-addressed object storage. Database records contain identity, hashes, state, ownership, and access policy. Evidence references immutable artifacts rather than embedding source code or secrets in model messages.
