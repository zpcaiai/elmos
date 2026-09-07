# Batch 9 behavioral-equivalence protocol

## Contents

1. Admission and authority boundary
2. Observable Behavior Model and scenarios
3. Dual-runtime control and nondeterminism
4. Collection, canonicalization and Oracle decisions
5. Domain-specific comparisons
6. Golden, tolerance, privacy and Agent governance
7. Evidence, Batch 8 feedback and gates

## 1. Admission and authority boundary

Require Batch 8 R-D admission, immutable source and target Snapshots, source baseline evidence,
module and business-capability scopes, unresolved Semantic Obligations, versioned scenarios,
registered observation points and an explicit policy. Keep the artifact workspace outside both
repositories. `modules/behavior-equivalence` is the authoritative control-plane contract.

Use `DualRuntimeAuthority`, `DifferentialExecutionAuthority`, `EquivalenceOracleAuthority` and
`Batch8RepairFeedbackAuthority` only as injected ports. The core does not execute customer code,
start a process, install a package, capture live traffic, access production, issue credentials,
approve a change or edit either repository. External implementations must run in approved,
isolated environments.

Reject shared mutable databases, schemas, sequences, cache namespaces, message destinations,
consumer groups, scheduler locks, files, buckets, ports, temporary directories or record/replay
sessions. Disable schedulers unless a scenario explicitly tests them. Readiness, cleanup and
collector failures are infrastructure states, not behavior regressions. `NOT_RUN`, `UNKNOWN`,
`NOT_COMPARABLE` and retry-then-pass never mean equivalent.

Batch 9 can admit a module to Batch 10 production hardening. It never authorizes production
cutover, traffic shift or source retirement.

## 2. Observable Behavior Model and scenarios

Model input, initial state, execution context, return/HTTP output, database and transaction
effects, messages, files/object storage, cache, external calls, exceptions, audit/log/metric
events, timing class, resource lifecycle and final state. Keep internal debug evidence separate
from externally meaningful behavior.

Build scenarios from source tests, contract tests, OpenAPI/message/database contracts, sanitized
samples, incidents, boundary values, property generators and reviewed critical cases. Include
success, invalid/missing/null/empty input, authorization, absence, duplicate/idempotent input,
concurrency, transaction failure, dependency failure, timeout, cancellation, retry/DLQ, corrupt
file, precision, timezone/DST and high-volume cases. Save generator seeds and minimal counterexamples.

Map every blocking obligation to at least one scenario and every expected effect to a required
observation point. Missing critical observation coverage blocks a high-level conclusion. Prioritize
security, money and transaction behavior, then public contracts, domain rules, messaging/data and
ordinary paths. Evaluate modules and business capabilities independently.

## 3. Dual-runtime control and nondeterminism

Align business configuration, feature flags, locale, timezone, database/schema/seed, cache,
message state, external responses, file permissions, runtime/dependency versions and identity/
tenant context. Record every intentionally different runtime property and whether it affects
comparability. Independent logical seeds may use ID mapping, but must preserve referential integrity.

Inject or adapt frozen, advancing or scripted application clocks. Distinguish UTC/local time,
wall/monotonic clocks, deadlines, TTL and calendar time. Exercise month/year end, leap year, DST,
timezone conversion, token/cache expiry, cron, timeout, clock rollback and precision without real waits.

Control random, UUID, sequence, temporary-path, hash-order and database-generated values with a
fixed seed, pre-generated stream, dependency injection, record/replay or reviewed semantic mapping.
Never put a fixed cryptographic seed into production code. For security random values, compare
format, length, uniqueness, properties and call count rather than exact bytes.

Virtualize HTTP/RPC/payment/email/SMS/identity and other external systems. Match requests on a
bounded method/path/query/header/body/business-key/session/correlation policy. Replay the same
response and virtual latency to both systems. Compare call count/order/retry. Never invoke a real
non-idempotent service. Include timeout, connection failure, 5xx, rate limit, partial/invalid
response, latency, duplicate, certificate and expired-token faults.

## 4. Collection, canonicalization and Oracle decisions

Collect before, during, after success/failure/rollback and after shutdown. Collectors must prefer
read-only access and must not change a transaction, consume/ack a real message, mutate a file,
trigger lazy business logic, extend resource lifetime, block a business thread or expose a secret.
Record collector version, logical sequence and raw evidence. A collector failure is not a source/
target difference.

Preserve raw and canonical values. Allow lossless normalization such as JSON object-field order,
insignificant XML whitespace, CRLF/LF, path separators, header case, equivalent float text and
one-to-one generated-ID mapping. Require explicit contract evidence for list sorting, time
truncation, exception mapping, ignored new fields, numerical tolerance or message ordering.

Never normalize or tolerate away permissions, tenant identity, HTTP status, error code, money/
Decimal, row/message count, transaction commit/rollback, data deletion, duplicate/lost messages,
audit/security events or arbitrary timestamps/collections. Scope every rule by observation and
field; version it; preserve pre/post values; do not retroactively rewrite approved evidence.

Combine exact, canonical, schema, contract, property, state transition, effect, metamorphic,
domain invariant and reviewed manual Oracles. A passed Oracle cannot cancel a failed required
Oracle. Preserve conflicts. Required `FAILED` means regression; `UNKNOWN` or `NOT_RUN` remains
unknown. Security, money and transaction scenarios require strict equivalence for E-D.

## 5. Domain-specific comparisons

- HTTP: compare status, meaningful headers, cookies and security attributes, content type/charset,
  body schema/value/presence/null/empty/numeric type/Decimal/array order, redirects, cache controls,
  streaming chunks/flush/midstream error and cancellation. Never merge 200/204 or 401/403.
- Database: compare logical entities, counts, keys, null/Decimal/time, relations, order, versions,
  soft delete, tenant, audit, aggregates, defaults, sequences, triggers and constraints. Equal
  aggregates cannot hide missing details.
- Transactions: compare begin/write/commit/rollback/savepoint/retry/lock/isolation/outbox and
  message-after-commit traces. Inject failure after writes, around message send and around commit.
  Equal final state cannot hide partial commit.
- Messages: compare destination/type/key/payload/header/schema/count, declared global/partition/
  aggregate/causal order, correlation/causation, retry/duplicate/ack/DLQ/offset, idempotency and
  consumer effects. Unordered never means missing is allowed.
- Files and storage: select byte, text, structured, archive-logical, domain-parser or reviewed
  perceptual comparison. Compare archive entries rather than physical ZIP bytes. Compare object
  key, content type, metadata, tags, version, ACL, encryption and lifecycle.
- Cache: compare namespace/key/value/serialization/TTL/sliding/hit/miss/put/evict/null/stampede/
  fail-open and transaction order with virtual time. Tenant key drift is critical.
- Failure semantics: distinguish success/failure timing, channel, logical/runtime type, code,
  structured message, cause, HTTP mapping, retryability, rollback, visibility, timeout and
  cancellation. Runtime exception classes may map; swallowed errors may not.
- Audit and concurrency: require business/audit/security/compliance events and correlation while
  allowing framework debug-format variation. Test races, lost updates, duplicate work, deadlock,
  cancellation and convergence with explicit happens-before/partial-order rules and finite bounds.

## 6. Golden, tolerance, privacy and Agent governance

A Golden contains input, initial state, environment, raw and canonical observations, normalization
profile, fixed source Snapshot and human review. States are candidate, captured, reviewed, approved,
deprecated, invalidated, superseded or rejected. Source bug, contract/flag/schema/input/clock/random/
recording/rule changes invalidate it. Never generate a Golden from target output or overwrite raw
history. Update a Golden through diff, review, reason, version and rollback.

Scope tolerance to one scenario, observation and field; record type/value/floor, rationale,
approver, evidence and expiry. Do not use tolerance for security, money, status, counts,
transactions, audit or tenant isolation. Keep `APPROVED_CHANGE` separate from equivalent; record
business reason, compatibility/version/release strategy, caller impact, tests, rollback, approver
and activation. Agent output cannot add tolerance, approve a change, modify a Golden or close an
obligation.

Classify data as public, internal, confidential, personal, sensitive, credential, financial,
medical, security or regulated. Mask/hash/tokenize/pseudonymize/synthesize/drop/encrypt while
preserving cross-observation references. Delete credentials and reissue test identities; do not
merely mask tokens or keys. Scan every export, enforce access/retention/deletion and store no real
secret in traffic, snapshots, messages, logs, files or Golden evidence.

Use a constrained diagnostic Agent only on minimal redacted evidence. It may propose causes,
observations, reproductions, tests and a Batch 8 repair candidate. It cannot adjudicate equivalence,
weaken an Oracle, make a high-risk edit or claim a source bug without evidence. Keep `UNKNOWN`
when proof is insufficient.

## 7. Evidence, Batch 8 feedback and gates

Preserve source/target Snapshots, environment manifest, raw/canonical input and observations,
initial state, raw/canonical diffs, rules, clock/seed, external recordings, collector states,
root cause and reproduction commands. Every blocking difference needs an immutable, redacted,
sandbox-reproducible package. Do not substitute screenshots for machine evidence.

Classify differences as equivalent, equivalent-after-normalization, within-tolerance,
approved-change, regression, unknown or not-comparable. Detect source/target/both nondeterminism,
environment or collector noise and true races across repeated clean runs. A flaky difference
cannot close an obligation or enter the permanent corpus. Promote only reviewed, stable,
source-confirmed, fixed, fully observed and production-independent cases.

Cluster regressions by evidenced root cause and emit bounded Batch 8 repair feedback. Preserve
source-bug candidates and environment/collector problems outside the migration-regression count.

- E-A: ready isolated runtimes; aligned state/config/time/random/external responses; complete
  critical observation points; no critical not-comparable scenario.
- E-B: E-A plus all critical HTTP scenarios, endpoint equivalence at least 0.99, and zero security,
  validation or error-contract regression.
- E-C: E-B plus critical database equivalence 1.0 and zero transaction atomicity, critical message,
  file or audit regression.
- E-D: E-C plus critical scenario acceptance 1.0, required acceptance at least 0.98, zero unapproved
  change/open blocking obligation/critical unknown, strict security-money-transaction behavior and
  at least two matching clean runs.
- E-E: E-D plus required acceptance, observation and source-target trace coverage at least 0.995,
  property and metamorphic pass rates at least 0.99 and flaky difference rate at most 0.005.

Repository averages cannot hide one failed module. Keep approved change distinct from equivalent,
flaky distinct from stable, and HTTP distinct from side effects. E-D/E-E only admit the module to
Batch 10 production hardening; always set cutover eligibility to false.
