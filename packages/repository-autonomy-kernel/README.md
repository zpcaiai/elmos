# Elmos Repository Autonomy Kernel

One package, two engines, one contract. The v2.0.0 specification declares 31
capabilities; this package implements all of them and can tell you, per skill,
which implementation answered and why.

```text
 40775 lines  src/elmos_autonomy_kernel/       capability core: the algorithms and invariants
 10665 lines  src/elmos_repository_autonomy/   platform: store, external adapters,
                                                certification, deployment, HTTP
 24568 lines  tests/                           1,558 tests, 0 failures
  1191 lines  sql/                             32 control-plane tables + the core's streams
```

Two sessions built this contract independently and neither result was thrown
away. `docs/MERGE_DECISIONS.md` records what won where and on what evidence -
including the four places the *platform* half won and kept the job, and the two
rationales that turned out to be wrong about it.

## Which engine answers what

```bash
elmos-autonomy engines        # the routing table, with a written reason per row
```

Every dispatch result carries `ENGINE:kernel` or `ENGINE:legacy` in its reasons,
so a result never leaves you guessing which of two implementations produced it.
Sixteen skills route to the capability core today; the rest answer from the
platform engine, and that is a decision per skill rather than an oversight.

Three rules keep the delegation safe, enforced in `kernel_bridge.serve`:

1. A core **domain** rejection is never downgraded to a legacy success.
2. A core **decode-level** refusal is a gap in the bridge's own translation, not
   a verdict about the caller - it falls through and is recorded as
   `KERNEL_INPUT_UNMAPPED:<code>`, countable rather than silent.
3. An adapter may **derive** a field implied by what the caller sent; never
   **invent** one. Deriving an environment fingerprint from the submissions it
   polices would turn the check into a tautology, so those adapters refuse.

## The rules the capability core is built on

1. **Fail closed.** Unknown field, tool, model or policy is a denial. An empty
   policy set denies. Nothing is allowed because nothing said no.
2. **No silent zero.** Zero is a legal business value. An unmeasured quantity is
   reported as unmeasured (`null` plus `measured: false`), never as `0`. This
   defect class has shipped three times in this repository.
3. **No floats** in anything hashed, compared, budgeted or persisted.
4. **`SUCCEEDED` != `PARTIAL` != `INTERRUPTED` != `FAILED`.** No path widens one
   into another.
5. **Determinism.** Same inputs, byte-identical outputs.
6. **Staleness is an error**, for snapshots, policies, authorities and leases.

## Running it

```bash
python3 -m pytest tests -q                       # 1,651 tests
elmos-autonomy engines                           # routing table + why each row routes there
elmos-autonomy catalog                           # the 31 declared capabilities
elmos-autonomy serve --port 8080                 # HTTP control plane
elmos-autonomy postgres-migrate --dsn ...        # apply sql/migrations
make -C ../.. repository-autonomy-kernel         # the repository gate
```

### The evidence seal key

`serve` refuses to start without one. That is deliberate: a server that boots
without a seal key evaluates *every* release gate to `EVIDENCE_UNVERIFIABLE`
while reporting itself healthy, and the failure then reads as a property of the
bundles being submitted rather than of the deployment.

```bash
openssl rand 48 > /run/secrets/elmos-seal.key   # 32 bytes minimum
chmod 0400 /run/secrets/elmos-seal.key
export ELMOS_AUTONOMY_SEAL_KEY_FILE=/run/secrets/elmos-seal.key
elmos-autonomy serve --port 8080
```

**The variable names a path. It never holds the key.** A secret placed in the
environment is inherited by every child process this package spawns — and
`deployment.SubprocessCommandRunner` exists to spawn some — is readable at
`/proc/<pid>/environ` by anything running as the same user, and is captured
verbatim in core dumps, `kubectl describe pod`, `docker inspect` and most CI
logs. A file can be mounted read-only from a secret store and unmounted.

A single trailing newline is stripped, because every ordinary way of creating
the file adds one and a key that silently differs from the sealing side's
produces `BUNDLE_SEAL_INVALID` on every bundle with nothing pointing at the
cause. Interior bytes are used exactly as written.

For a deployment that does not evaluate release gates, `serve --no-seal-key` is
the explicit opt-out — so running without a key is a stated choice rather than
an omission. `elmos-autonomy dispatch` binds the key only if one is configured,
because a one-shot `repository-census` should not be blocked on a secret it
never touches.

### Where data actually goes

`postgres-migrate` applies 37 tables. **23 of them have no writer anywhere in
the package** — including `autonomy_runs` and every table that foreign-keys to
it. The dispatcher's run state goes to SQLite through `storage.DurableStore`,
under bare names (`runs`, `events`, `leases`). The only PostgreSQL paths are
`PostgresWaveStore` (external operations, inbox/outbox, certification, customer
acceptance, secret leases) and the capability core's five `autonomy_kernel_*`
tables.

A schema that advertises a control plane which is not there is worse than a
missing one: it gets read, believed, backed up and audited. `sql/README.md` has the full table, and
`tests/test_persistence_split.py` pins which tables have an implementation and
which do not, failing if either list moves without the other. Closing the split — implementing the 23 against
PostgreSQL, or not shipping them — is an open architecture decision.

## Durability evidence

The in-memory and PostgreSQL adapters run the *same* conformance suite, because
an invariant that holds in one process and dissolves under two connections was
never an invariant:

```bash
ELMOS_KERNEL_PG_DSN=postgresql://... python3 -m pytest tests/test_adapter_conformance.py -q
ELMOS_KERNEL_PG_DSN=postgresql://... PYTHONPATH=src python3 scripts/durability_evidence.py
```

The evidence script is not a unit test. It starts a child process, has it commit
a side-effect *intent* to a real server, and kills that process with `os._exit`
at the exact point a real executor dies - after the intent is durable and before
the observation is written. A fresh process on a fresh connection then rehydrates
the run and must report: the chain verifies, the state is not `SUCCEEDED`, the
side effect is `unresolved`, and the rollback plan is `complete: false` naming
that step. Recorded output: `evidence/durability-postgres16.json`
(PostgreSQL 16.13).

That run also found a defect no unit test could: `KernelError` was a frozen,
slotted dataclass, so Python could not attach a traceback to it and every error
propagating out of a database transaction was replaced by an unrelated
`TypeError`. `tests/test_errors_foundation.py` pins it.

## Layout

```text
src/elmos_autonomy_kernel/          31 capability modules + ports + adapters
src/elmos_repository_autonomy/      dispatcher, store, external, certification,
                                    deployment, server, kernel_bridge,
                                    kernel_store_adapter
sql/migrations/                     V001-V006 control plane, V007 core streams
contracts/openapi/                  4 API contracts
policies/rego/                      4 policy modules
deployment/                         Dockerfile, Helm, K8s, CI gates
docs/MERGE_DECISIONS.md             what won where, and on what evidence
docs/REUSE_MAP.md                   31 capabilities vs what ELMOS already had
docs/IMPLEMENTATION_CONTRACT.md     the standard the capability core was written to
scripts/durability_evidence.py      the crash-recovery run
```
