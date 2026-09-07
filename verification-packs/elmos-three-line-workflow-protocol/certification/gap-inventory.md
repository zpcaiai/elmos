# Gap inventory

The local model, negative traces, real local Git fixture, durable-lease tests,
browser journeys, and CI replay command are implemented. The exact remaining
gates are external and must not be inferred from this pack:

- Execute GitHub and Gitee provider operations with approved short-lived
  credentials in isolated test organizations.
- Exercise lease expiry and worker loss across at least two replicas on the
  actual shared storage topology.
- Run the immutable holdout corpus with an independent verifier.
- Run representative production-scale workloads with approved privacy,
  capacity, rollback, and incident-response controls.
- Bind resulting raw evidence and approvals before any status beyond
  `experimental` / `NOT_CERTIFIED` is considered.
