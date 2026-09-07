# Failure Injection Matrix

| Failure | Expected invariant |
|---|---|
| Worker dies after solver success before commit | run is retried; no success without durable evidence |
| Worker loses lease then commits | stale fencing token rejected |
| Database commit succeeds, event publish fails | outbox republishes once logically |
| Object upload succeeds, DB commit fails | orphan is not evidence and is collected |
| Duplicate usage event | charged at most once |
| Pause during proof | checkpoint or safe restart; no duplicate committed effect |
| Cancel during artifact upload | partial artifact never marked final |
| Assumption changes during run | result is rejected or immediately stale |
| Solver timeout | `UNKNOWN_TIMEOUT`, not PASS |
| Solver returns malformed output | infrastructure failure, raw output retained |
| Network partition | no split-brain owner commit |
| Tenant ID injection | RLS/object/cache isolation rejects |
| TCB image revoked | dependent evidence stale and gate reevaluated |
| Clock skew | lease policy uses authoritative time or explicit tolerance |

E4 certification executes these cases against the real durable workflow, database, object store, event bus and billing service.
