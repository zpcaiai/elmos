# Batch 46 — Runtime lease policy

## The rule

A one-click smoke run gets **10 minutes of free runtime**. When the lease
expires, every service the run started is stopped, every container and volume it
created is removed, and every byte of smoke data it wrote is deleted.

A smoke run is a lease, not a deployment. That is what makes it safe to tell a
recipient "just run it" — the worst case is that they lose ten minutes, not that
they leave a seeded database and an open port behind on their laptop.

## Parameters

| Field | Default | Notes |
| --- | --- | --- |
| `free_quota_seconds` | 600 | fixed; validation rejects any pack that changes it |
| `ttl_seconds` | 600 | the granted lease; `--ttl` may shorten it freely |
| `grace_seconds` | 30 | SIGTERM to SIGKILL window |
| `auto_renew` | `false` | never true |
| `extend_policy` | `explicit-only` | requires `--seconds`, `--reason`, `--actor` |
| `billable_seconds` | `max(0, ttl - free_quota)` | recorded, not charged, by Batch 46 |

## Enforcement

The watchdog runs independently of the application under test. It does not ask
the application to stop; it stops it.

1. At expiry the watchdog sends `SIGTERM` to each managed process **group** —
   process groups, not PIDs, so a wrapper like `npm run start` cannot leave its
   child listening.
2. Processes that have not exited after `grace_seconds` are `SIGKILL`ed and the
   run is recorded as having failed its graceful-shutdown assertion. Being killed
   is a finding, not a cleanup detail.
3. `docker compose down -v --remove-orphans` runs for every tracked compose file.
4. Every tracked ephemeral path is deleted.
5. A `lease-result.json` is written on expiry, early release, Ctrl-C and handled
   termination. An uncatchable host/process loss cannot manufacture a receipt;
   its missing result remains a cleanup incident and blocks the gate. Teardown
   is idempotent and safe to invoke twice.

The `lease-teardown` assertion then verifies the outcome rather than trusting
it: no live process, no undeleted path, no compose failure, and the port no
longer accepting connections. Residue fails the run.

## Extension

Extension is deliberate friction. There is no auto-renew and no "keep alive"
flag, because a smoke environment that quietly becomes permanent is how seeded
fixture data ends up in something that matters.

```bash
python3 smoke/tools/smoke_lease.py extend --project . --seconds 300 \
    --reason "reproducing the 500 on POST /orders" --actor "ethan"
```

Both `--reason` and `--actor` are mandatory: an extension is an attributable
decision. Seconds granted beyond the free quota accumulate in
`billable_seconds`, the gate downgrades the run to `limited`, and metering
belongs to Batch 44 — Batch 46 only records the number.

## Early release

```bash
python3 smoke/tools/smoke_lease.py stop --project . --reason manual
```

Ctrl-C during the hold does the same thing. Early release is the normal, encouraged
path — the lease is a ceiling, not a target.

The external `stop` command writes a bounded stop request into the lease and waits
for the originating watchdog to acknowledge it. It does not reconstruct a second
watchdog from serialized PIDs and paths: that would race the owner, lose real
process handles, and could turn a corrupt lease into an arbitrary kill/delete
instruction. A controller that does not acknowledge within the grace window
returns failure and produces no successful teardown receipt.

## What the lease does not cover

The lease governs what the smoke run started. It cannot reclaim a service the
operator started themselves, a shared database the `script` entry was pointed at,
or anything a project's own start command spawns outside its process group. Where
a project detaches its own daemons, that is recorded as an unresolved unknown
and blocks certification rather than being papered over.
