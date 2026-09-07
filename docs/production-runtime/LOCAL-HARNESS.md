# Production Runtime Local Qualification Harness

`make production-runtime-local` runs repository-owned qualification code for
the parts of the production gate that can be reproduced safely on a developer
host:

- the provider-neutral adapter state machine proves complete, replay,
  rejected, and `UNKNOWN` outcomes without using a provider SDK or credential;
- PostgreSQL Testcontainers runs durable dispatch, billing, RLS, recovery,
  Chaos Matrix, Redis-loss, worker-process-kill, and bounded reserve-load tests;
- `scripts/production-runtime/run_pitr_drill.py` takes a disposable physical
  base backup, replays WAL to a target LSN, and proves post-target data is not
  restored;
- `scripts/production-runtime/verify_local_harness.py` independently checks
  the report digest, source-package binding, exact local scenario inventory,
  and the non-certification boundary.

The runner writes logs and content-addressed reports below `.elmos/`, which is
ignored as generated evidence. The report marks these results as
`LOCAL_HARNESS_PASS`; it deliberately keeps real Provider, target-cluster
load, production chaos, hosted Redis, hosted backup/PITR, independent external
verification, production deployment, and production certification as
`NOT_RUN` / `NOT_CERTIFIED`.

The attached skill archive remains declarative input. The harness does not
execute archive scripts, installers, prompts, or workflows.
