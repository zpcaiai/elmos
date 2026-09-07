# Skill: Elmos Production Repository Execution OS

## Use this skill when

Implementing, reviewing, migrating, testing or operating Elmos for repository-scale AI engineering workloads, especially:

- Spring legacy modernization;
- whole-repository cross-language conversion;
- multi-language project generation;
- SQL dialect / routine conversion;
- repository refactoring and future workload packs using the same kernel.

## Mandatory aggregate model

Use:

`Tenant -> Account -> Project -> Job -> Stage -> WorkItem -> DispatchIntent -> Attempt -> ModelCall/ToolCall`

Never collapse Project, Job, WorkItem, Attempt or ModelCall into one record.

## Source of truth

- PostgreSQL: durable execution, accounting, ownership, lineage, events.
- Redis: optional cache / semaphore / rate limiter only.
- S3/MinIO/Object Storage: large source archives, AST/IR, patches, logs, reports, binaries.
- Projections are rebuildable and never determine billing or ownership truth.

## Dispatch Saga

Never call Billing while holding scheduler DB locks.

Required flow:

1. `READY -> RESERVING`
2. persist `dispatch_intent`
3. commit
4. Billing reserves credit using stable idempotency key
5. persist reservation id in intent and mark `RESERVED`
6. create Attempt, Lease and monotonic Fence
7. `RESERVED -> DISPATCHING`
8. dispatch to addressable Worker
9. worker ACK -> `RUNNING`
10. dispatch failure -> release reservation + retry
11. scheduler crash -> reconciler resumes from intent state

## Financial flow

Prepaid work:

`estimate -> reserve -> execute -> stream meter -> final usage -> settle -> release unused -> ledger/journal`

Never run billable work first and deduct later.

## Provider call idempotency

Financial dedupe is not enough. A retried Elmos request must not call a model provider twice.

Persist a `model_call_receipt` keyed by Elmos idempotency key / provider request identity. Replays return the existing committed/provider-known call status/result, or reconcile provider state before retrying.

## Streaming usage

During long calls write monotonic usage meter events:

- cumulative input tokens
- cached input tokens
- output tokens
- reasoning tokens
- provider cost estimate
- customer credit estimate

Final settlement must reconcile the meter stream against final provider usage.

## Worker fencing

Every worker completion must include:
- work_item_id
- attempt_id
- fencing_token

Commit succeeds only if the current lease matches all three.

Zero affected rows means stale ownership and must return conflict.

## Worker addressing

If scheduler targets a specific registered worker, workers must be individually addressable:
- StatefulSet + headless service;
- direct worker endpoint registry;
- or queue-consumer identity with equivalent ownership semantics.

Do not use a random load-balanced Service when exact worker identity is required.

## Billing ownership

Only BillingService may mutate:
- wallet balances
- reservations
- top-ups
- usage events
- ledger
- journals
- pricing versions
- refunds/adjustments

## Idempotency

Use a dedicated idempotency table with:
- tenant
- operation
- key
- request hash
- status
- response payload
- resource id
- expiry

Same key + different request hash must be rejected.

## Top-up

Top-up is a first-class accounting flow:

`PaymentReceipt -> TopUp -> Wallet -> Ledger -> Journal -> Outbox -> CreditResume`

Duplicate payment provider notifications must not double credit.

## Recovery

Implement reconcilers for:
- RESERVING
- RESERVED
- DISPATCHING
- expired leases
- orphan reservations
- model calls with uncertain provider outcome
- unpublished outbox
- WAITING_FOR_CREDIT after top-up

## Completion

Generation alone is not success.

Typical gate:
`generate -> build -> test -> behavior/contract diff -> repair -> retest -> package -> report`

## Required production tests

- ConcurrentReserve
- DuplicateUsage
- DuplicateProviderCallReplay
- IdempotencyConflict
- StaleFence
- LeaseExpiry
- SchedulerRestartAtEveryDispatchState
- CreditExhaustionResume
- TopUpReplay
- RedisLoss
- RLSIsolation
- ProjectorReplay
- BillingReconciliation
- JournalBalance
- StreamingUsageReconciliation
- PITRRestore
- ChaosMatrix
