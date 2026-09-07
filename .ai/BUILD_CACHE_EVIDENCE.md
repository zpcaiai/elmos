# Build-cache v1.2 evidence ledger

This file records executed engineering evidence for every BC task. The
authoritative status and complete BC-01…BC-30 matrix are in
`BUILD_CACHE_PROGRESS.md`; this file is the acceptance/evidence view of the
same synchronized snapshot.

- Snapshot: **2026-08-26 Asia/Shanghai**
- Branch: `perf/analyzer-build-cache-and-batching`
- Code SHA: `ea894caacf414a2676226c8297d6e5fcfd9c569b`
- Archive SHA-256: `dde312b55a95cbc7af6753ec88f07833e93ffa296b782ddcf3ef1a6470b73cb7`
- Local PostgreSQL receipt SHA-256: `sha256:d1d055932032e23dd0a2c181ff1bd7ca3e64847325b28792fcfa49c52fcb3503`
- External evidence: `NOT_RUN`; certification: `NOT_CERTIFIED`

The input ZIP is untrusted. Its scripts, installers, validators, workflows,
prompts and examples were inspected as data but not executed. Local test and
qualification results below are self-attested engineering evidence and do not
prove provider behavior, production safety, independent verification or
Codex/Claude equivalence.

## Acceptance coverage

| Evidence area | Implementation bound to | Executed check | Result |
| --- | --- | --- | --- |
| Package identity and retention | Pinned ZIP, immutable extraction, four-root manifest | Independent importer/checksum/DAG validation; second import | `COMPLETE_VERIFIED` — 42 Skills, 31 retained + 11 new, four roots byte-identical |
| Prompt boundary | `prompt_runtime.py`, prompt compiler and provider-safe API | Prompt integration tests in focused pack; content-free response assertions | `COMPLETE_VERIFIED` — explicit `CACHE_BOUNDARY`, payload never returned by control plane |
| Context ledger | `context_runtime.py`, append-only events and checkpoint projections | Context runtime and API integration tests | `COMPLETE_VERIFIED` — scope/provenance/source digests checked |
| Environment cache | `environment_runtime.py` and CAS metadata | Environment runtime tests | `COMPLETE_VERIFIED` — sealing, restore, quarantine, revoke and cleanup paths |
| Affinity and diagnostics | `affinity_service.py`, `diagnostic_runtime.py` | Affinity/diagnostic tests | `COMPLETE_VERIFIED` — local singleflight and closed miss taxonomy |
| Parity metadata/API | `parity_store.py`, `parity_api.py` and canonical schemas | Parity store/API tests, reopen/idempotency/tenant negatives | `COMPLETE_VERIFIED` |
| Harness and jobs | `parity_jobs.py` and durable source/result events | Harness/job tests, replay and outcome-unknown reconciliation | `COMPLETE_VERIFIED` |
| Five-layer composition | `parity_composition_root.py`, `parity_composition_wiring.py` | Composition-root/wiring tests, signed scope/deadline/subset checks | `COMPLETE_VERIFIED` |
| SLO state machine | `slo_service.py`, `db/store.py` and API routes | SQLite SLO suite plus live PostgreSQL qualification | `COMPLETE_VERIFIED` locally; external production evidence `NOT_RUN` |
| GC reachability | `gc.py` roots for SLO/layers/jobs | GC and parity-store tests | `COMPLETE_VERIFIED` |
| OpenAPI contracts | Root OpenAPI and packaged `_data` mirror | `cmp -s` and YAML parse; job routes present | `COMPLETE_VERIFIED` — byte-identical, 8 paths |

## BC task evidence index

The following rows intentionally repeat the complete task identity so a reader
of this evidence file can audit coverage without guessing which task a result
belongs to. Detailed implementation and remaining boundaries are maintained in
`BUILD_CACHE_PROGRESS.md`.

| Task IDs | Evidence state | Evidence pointer |
| --- | --- | --- |
| BC-01…BC-04 | `COMPLETE_VERIFIED` | Pinned archive digest, 42-Skill manifest, checksum/DAG/importer replay |
| BC-05, BC-20 | `COMPLETE_VERIFIED` | Prompt compiler, stable prefix, explicit cache boundary and local linter tests |
| BC-06, BC-21 | `COMPLETE_VERIFIED` | Context ledger, complete event projector, checkpoint/CAS scope tests |
| BC-07, BC-22 | `COMPLETE_VERIFIED` | Environment identity/seal/restore/quarantine/cleanup tests |
| BC-08, BC-23, BC-24 | `COMPLETE_VERIFIED` | Affinity singleflight, placement identity and content-free diagnostic tests |
| BC-09 | `COMPLETE_VERIFIED` | Exact parity evaluator/harness shape and evidence-binding tests |
| BC-10, BC-11 | `COMPLETE_VERIFIED` | Durable metadata/API and pre-idempotency tenant/project/principal negatives |
| BC-12, BC-26 | `COMPLETE_VERIFIED` | Trusted harness, durable job receipts, source-event verification and replay |
| BC-13, BC-27 | `COMPLETE_VERIFIED` | SLO state machine, typed errors, stale-head fence and PostgreSQL receipt |
| BC-14, BC-25 | `COMPLETE_VERIFIED` | Five-layer signed composition root/wiring and outcome sink tests |
| BC-15 | `COMPLETE_VERIFIED` | Provider prompt prepare/usage API, OpenAPI and idempotency reconciliation |
| BC-16 | `PARTIAL_WITH_HOST_BLOCKER` | Mac focused pack is green; one unrelated historical full-suite blocker and native gaps remain |
| BC-17, BC-30 | `COMPLETE_VERIFIED` | Code commit plus synchronized six-file documentation closeout; final push verification pending at write time |
| BC-18 | `NOT_RUN` | No production-equivalent provider/image/fleet/corpus/rollout receipt |
| BC-19 | `NOT_CERTIFIED` | Conservative external gate is intentionally not asserted |
| BC-28 | `COMPLETE_VERIFIED` | SLO/parity layer/job retention roots included in reachability |
| BC-29 | `COMPLETE_VERIFIED` | Disposable PostgreSQL 17.5 receipt, metadata 65/65 and SLO 3/3 |

## PostgreSQL qualification evidence

The qualification tool created a disposable cluster below `/tmp`, exposed only
through a mode-0700 Unix socket, with `fsync=on` and
`synchronous_commit=on`. It accepted no caller DSN, recorded no secret and did
not write production data. The receipt binds the source revision exactly to
`ea894caacf414a2676226c8297d6e5fcfd9c569b`.

```text
metadata-store: 65 passed, 0 skipped, 0 failed
slo-service-live-postgres: 3 passed, 0 skipped, 0 failed
PostgreSQL: 17.5 (Homebrew)
CPython: 3.12.12    psycopg: 3.3.4
teardown: COMPLETE
evidence class: LOCAL_EXECUTED_SELF_ATTESTED
CI / production / independent verification: NOT_RUN
```

Database evidence is additionally bound by migration-ledger digest
`sha256:2e97c7d985fb5a8a8345512295ffa238722b38ec30a218c582cbf2848c92f23d`
and schema-introspection digest
`sha256:5db22f9d2b18974b3ae0d45a96848adb0a3d17e1ffe6c6657f75bb2597d8c7b4`.

## Evidence limitations

- The current focused Mac pack is `279 passed, 3 skipped`; it is not a
  certification gate and its three skips remain explicit.
- A prior consolidated non-native run recorded `1734 passed, 51 skipped, 1`
  unrelated pre-existing policy failure. It is historical aggregate evidence,
  not a new run and not silently converted to green.
- The native-toolchain sweep was interrupted and is `NOT_RUN/INCOMPLETE`.
- Real providers, SDK/model cache accounting, production PostgreSQL, external
  images, multi-host fleet, representative/holdout corpus, CI and rollout are
  all `NOT_RUN`.
- No number above certifies parity or production readiness.
