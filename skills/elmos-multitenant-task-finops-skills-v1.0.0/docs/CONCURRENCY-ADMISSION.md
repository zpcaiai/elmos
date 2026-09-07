# Concurrency Admission and Performance

## 1. Product rule

Every authenticated account can execute at most **three root tasks concurrently across all tenants**. A root task may contain many internal nodes, but node parallelism is separately controlled.

The fourth and later submission is accepted durably and placed in `WAITING_FOR_SLOT`. This avoids data loss and gives the UI a queue position while preserving the hard execution limit.

## 2. Why a database slot semaphore

Unsafe:

```text
count active tasks
if count < 3:
    start task
```

Safe:

```text
lock one of exactly three account slot rows
claim it and transition task in the same transaction
```

The database constraint is global across:

- API replicas;
- browser tabs;
- mobile/desktop clients;
- retries;
- automation clients;
- tenant switches;
- service restarts.

Redis may cache `2/3` for UI speed, but PostgreSQL decides.

## 3. Atomic admission transaction

Pseudo-flow:

```text
BEGIN
  SET LOCAL app.account_id = verified account
  SET LOCAL app.tenant_id = authorized tenant

  find/create task by scoped Idempotency-Key

  if task already exists:
      return existing task

  evaluate static policy and tenant queue limit
  create immutable task as CREATED

  ensure slot rows 1..3

  lock one free or expired-reclaimable slot
    FOR UPDATE SKIP LOCKED

  if no slot:
      task -> WAITING_FOR_SLOT
      record ACCOUNT_LIMIT reason
  else:
      evaluate tenant resource/budget/platform gates
      if all pass:
          claim slot with new lease_generation
          task -> ADMITTED
      else:
          do not retain account slot
          task -> WAITING_FOR_SLOT
          record all durable gate reasons

  append event/audit/outbox
COMMIT
```

Tenant/platform gates should be evaluated in an order that avoids holding an account row lock during slow external checks. Cache or precompute provider capacity and budget state; final durable checks occur inside the transaction.

## 4. Promotion

A task becomes eligible when:

- it is `WAITING_FOR_SLOT`;
- the account has a free slot;
- its tenant quota permits it;
- its workload queue/platform capacity permits it;
- budget/provider/security gates permit it;
- dependencies or approvals are satisfied.

Scheduling policy:

1. weighted fair selection across tenants;
2. priority plus aging within tenant;
3. FIFO tie-breaker by submission time;
4. account slot claim;
5. tenant/resource reservation;
6. `ADMITTED` transition;
7. workflow start intent.

The account slot must be released if a later gate fails before durable admission.

## 5. Resource units

A three-task count alone is insufficient. Example:

- documentation task: 1 unit;
- repository parse: 2 units;
- project generation: 4 units;
- full conversion/modernization: 8 units;
- GPU-heavy multimodal analysis: class-specific GPU units.

Actual values must be calibrated from measured resource usage. Store both estimate and actual. Tenant and platform quotas use units, while the account hard cap remains three root tasks.

## 6. Workload queues

Recommended Temporal queues:

```text
task-control
repository-io
parse-index
architecture-analysis
code-generation
code-conversion
model-inference
verification-test
render-export
private-runner
finance-projection
reconciliation
```

Each worker deployment sets bounded:

- workflow concurrency;
- activity concurrency;
- poller count;
- per-task fan-out;
- CPU/memory/GPU request and limit;
- provider request/token rate;
- retry concurrency.

Do not share one unbounded worker pool for all workloads.

## 7. Backpressure

Admission reasons are structured:

```text
ACCOUNT_ACTIVE_LIMIT
TENANT_ACTIVE_LIMIT
TENANT_QUEUE_LIMIT
TENANT_RESOURCE_LIMIT
TASK_BUDGET_LIMIT
TENANT_BUDGET_LIMIT
PROVIDER_RATE_LIMIT
PROVIDER_BUDGET_LIMIT
WORKLOAD_CAPACITY
RUNNER_SITE_CAPACITY
MAINTENANCE
DEPENDENCY_WAIT
APPROVAL_WAIT
SECURITY_POLICY
```

The UI and API expose all applicable reasons, not a generic "busy".

## 8. Database performance

- Use short transactions for slot claim/release.
- Never perform uploads, provider calls, or Temporal RPCs while holding slot locks.
- Index active task states and queued tasks.
- Use `SKIP LOCKED` for independent scheduler workers.
- Use outbox rather than synchronous event-bus publication in the task transaction.
- Batch non-critical progress events and logs.
- Store large payloads outside PostgreSQL.
- Use connection pools sized below database capacity; do not create one connection per workflow.
- Use event/signal-driven wake-up rather than one-second polling.
- Separate read-heavy analytics from hot admission queries if measured contention appears.

## 9. Fairness and starvation

Weighted fair scheduling prevents one tenant from monopolizing capacity. Priority aging prevents long-waiting tasks from starving.

Record:

- tenant virtual finish time or deficit;
- task effective priority;
- queue-entered time;
- promotion attempts;
- reasons skipped;
- estimated start P50/P90.

A scheduler decision must be explainable.

## 10. Slot reconciliation

The reconciler periodically verifies:

```text
number of occupied slots per account <= 3
occupied slot references a real task
occupied task state should consume a slot
lease generation matches active workflow/run
lease has not expired without recovery transition
terminal/paused task has no occupied slot
active task has exactly one occupied slot
```

Fixes use compare-and-set and append reconciliation events. Ambiguous cases go to manual recovery.

## 11. Load test matrix

| Scenario | Purpose |
|---|---|
| 100 simultaneous creates, one account | Prove max three |
| 1,000 accounts × burst | Admission throughput |
| One account across five tenants | Prove global account scope |
| One tenant with many accounts | Tenant quota and fairness |
| Heavy + light workload mix | Resource-unit behavior |
| Retry storm | Worker and database bounds |
| Event bus outage | Outbox backlog behavior |
| Database failover | Transaction/retry correctness |
| Slot lease expiry | Reaper and stale generation fencing |
| Queue backlog | Aging, ETA, and no starvation |
| Scale-out API replicas | Distributed race correctness |

## 12. Performance targets

Initial targets to validate and tune:

- task submission/admission decision P95 ≤ 500 ms excluding file upload and external identity latency;
- account slot claim P95 ≤ 50 ms under representative contention;
- progress UI propagation P95 ≤ 2 s;
- outbox publication lag P95 ≤ 2 s under normal load;
- zero account oversubscription;
- no unbounded queue or worker concurrency;
- progress persistence overhead ≤ 5% representative task wall-clock;
- graceful degradation with explicit admission reasons during saturation.

These are target gates, not production claims until measured in the target environment.
