# Repository runtime implementation contract

## Ownership and non-adoption

`V73__account_task_control_and_finops_runtime.sql` is authored for this
repository's Flyway history and canonical data model. It is not a renamed or
rewritten copy of the source package's `V100`-`V102` reference SQL. Those three
source migrations remain `NOT_APPLIED`. The existence of V73 is implementation
evidence only; it is not database-application, runtime, external, or
certification evidence.

V73 preserves these existing owners: `execution_jobs` and
`execution_job_events` for task truth; `accounts`,
`organization_memberships`, and `user_identities` for identity;
`content_objects` and `job_artifacts` for objects; and `usage_events` for usage.
It adds a revenue ledger because no canonical revenue truth previously existed.
Legacy jobs are account-bound only when organization plus actor resolves to one
exact active identity; ambiguous rows stay unresolved.

## Identity and isolation

- The control API obtains organization, account, and actor from the authenticated
  `ControlPlanePrincipal`, never from task paths, query parameters, request
  bodies, or tenant headers.
- `elmos_mtf_bind_identity` and `elmos_mtf_assert_bound_context` require one
  active account, membership, and user identity before scoped reads or writes.
  Missing or ambiguous context fails closed.
- MTF tables use organization/account foreign keys, FORCE RLS, revoked PUBLIC
  access, and NOLOGIN/NOBYPASSRLS capability roles. Security-definer functions
  expose the narrow mutation boundary.
- Finance writes additionally require an active `OWNER`, `ADMIN`, or `BILLING`
  membership. Public HTTP endpoints do not expose those writes.

This local implementation does not resolve the exact
`elmos-identity-tenant-security` dependency without its own binding and
execution receipt.

## Admission, queues, and the exact three-slot limit

- `execution_account_slots` owns exactly slots `1`, `2`, and `3` for every
  canonical account. Tenant plans may lower effective admission but cannot
  raise this platform-global maximum.
- Slot rows are claimed with transactional row locking. Lease reference,
  generation, expiry, job, organization, and account are fenced together.
- `ACTIVE` and `RECONCILING` slots consume capacity. A pause request continues
  to consume its running slot; a completed pause releases it. Unknown results
  retain a reconciling slot until their side effect is resolved.
- A fourth root job remains durable as `QUEUED` / `WAITING_FOR_SLOT`; it is not
  silently dropped or admitted by a process-local counter.
- Workload profiles are exact for `PARSING`, `GENERATION`, `CONVERSION`,
  `VALIDATION`, `RENDERING`, and `MODEL_GPU`, with versioned queue names,
  resource units, bounded worker concurrency, and autoscale bounds.
- The SQL claim order uses organization lease pressure, then priority, enqueue
  time, and job ID. The pure Java policy also defines weighted virtual service
  with priority aging. Runtime parity and contention behavior require real
  PostgreSQL evidence and are not inferred from source inspection.

Queue names and a workflow-start outbox do not establish Temporal operation.
No Temporal server, worker, history replay, nondeterminism, outage, or upgrade
receipt is bound, so `elmos-temporal-task-reliability` remains `UNRESOLVED`.

## Lifecycle, progress, pause, resume, and recovery

- Legal transitions and terminal immutability are enforced in both the pure
  policy and the database transition guard.
- Progress and elapsed time are monotonic. Non-success states are capped at
  99%; only `SUCCEEDED` may expose 100%. ETA P90 cannot be lower than ETA P50.
- Ordered events use per-job sequence numbers and idempotency keys. Progress,
  stage, lease, elapsed time, ETA, actor, and optional digest remain separate
  fields rather than being inferred from logs.
- Pause and resume require authenticated context, a reason, an idempotency key,
  a digest-bound request, legal state, and an append-only audit event. Resuming
  returns a paused job to `WAITING_FOR_SLOT`; it does not bypass admission.
- Checkpoints bind the input manifest, repository revision, toolchain, optional
  model, schema, state, and next node. The pure policy returns `FORK_RUN` for an
  incompatible identity; the current persistence adapter rejects incompatible
  idempotent replay. Automatic creation of the replacement run is not yet a
  repository-owned runtime effect and remains an explicit implementation gap.
- Side effects use append-only signed receipts. A lost lease or unknown effect
  transitions through `UNKNOWN_RESULT` and `RECONCILING`; absence of a receipt
  requires manual recovery. The current manual-reconciliation command records
  a pending request, not a fabricated outcome.

## FinOps exactness and finality

- Monetary fields use exact `numeric(30,6)` minor units. Usage quantity and
  unit price use `numeric(30,9)`; FX uses `numeric(30,12)`. Currency codes are
  explicit and cross-currency arithmetic is rejected without a bound FX
  snapshot.
- The Java money policy uses scale 6 and `HALF_EVEN`. PostgreSQL stores exact
  decimals and uses the repository-owned `elmos_mtf_round_half_even` helper for
  write-time recomputation and comparison. V73 contains positive and negative
  even/odd tie self-checks, and the disposable PostgreSQL migration test
  executes those checks. This is bounded local engineering evidence; broad
  cross-layer vectors, independent verification, and provider/bill parity
  remain `NOT_RUN`.
- Usage binds provider/SKU/unit, price book and version, effective time, price
  item, FX snapshot, period, cost class, state, and reconciliation status.
- Revenue recognition, cash collection, refund, cost, and allocation are
  distinct append-only records. Gross profit and margin never convert cash
  collection into recognized revenue; zero recognized revenue yields no margin.
- Allocation enforces currency/sign compatibility and prevents over-allocation.
  The pure policy conserves the scale-6 amount by assigning the deterministic
  rounding residual to the final ordered target.
- `UNKNOWN`, `INCONCLUSIVE`, `UNRECONCILED`, missing provider receipts, and
  incomplete allocation remain non-final. Manual/correction write paths remain
  unavailable while exact approval and segregation-of-duties dependencies are
  unresolved.

The related exact Skills `elmos-architecture-contract-governance`,
`elmos-identity-tenant-security`, `elmos-observability-finops`, and
`elmos-temporal-task-reliability` all remain `UNRESOLVED`. External evidence is
`NOT_RUN`, all 144 source task executions remain `NOT_RUN`, and production is
`NOT_CERTIFIED`.
