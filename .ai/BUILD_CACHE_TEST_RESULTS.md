# Build-cache v1.2 executed test results

This file is the test view of the synchronized BC-01…BC-30 ledger in
`BUILD_CACHE_PROGRESS.md`. Counts are from commands actually run; overlapping
historical runs are not added together.

- Snapshot: **2026-08-26 Asia/Shanghai**
- Branch: `perf/analyzer-build-cache-and-batching`
- Code SHA: `ea894caacf414a2676226c8297d6e5fcfd9c569b`
- Focused result: **279 passed, 3 skipped, 0 failed**
- Ruff: **All checks passed!**
- mypy: **Success: no issues found in 74 source files**
- OpenAPI mirror: **byte-identical; YAML parse successful; 8 paths**
- External provider/production/independent result: `NOT_RUN`
- Certification: `NOT_CERTIFIED`

## Focused cache pack

Executed from `engines/build-cache-engine`:

```bash
./.venv/bin/python -m pytest -o addopts=--strict-markers -q --tb=short \
  tests/test_context_runtime.py tests/test_prompt_runtime_integration.py \
  tests/test_affinity_service.py tests/test_parity_runtime.py \
  tests/test_parity_composition_root.py tests/test_parity_jobs.py \
  tests/test_slo_service.py tests/test_slo_api.py tests/test_api.py \
  tests/test_gc.py tests/test_api_composition_wiring.py \
  tests/test_environment_runtime.py tests/test_parity_store.py \
  tests/test_parity_api.py tests/test_diagnostic_runtime.py \
  tests/test_local_postgres_qualification.py
```

Result:

```text
279 passed, 3 skipped in 12.05s
```

The three skips are the live PostgreSQL test functions when the ordinary
focused invocation has no `ELMOS_TEST_POSTGRES_DSN`. They were then run by the
disposable qualifier below; the normal suite still does not pretend that a
missing DSN is production evidence.

## Static checks and contract checks

| Command | Result |
| --- | --- |
| `./.venv/bin/ruff check src tests tools` | `All checks passed!` |
| `./.venv/bin/mypy src` | `Success: no issues found in 74 source files` |
| `cmp -s openapi/cache-slo-control-plane.openapi.yaml src/elmos_build_cache/_data/openapi/cache-slo-control-plane.openapi.yaml` | exit `0` |
| YAML parse and route inspection | 8 paths; harness job and SLO job routes present |
| Staged/committed `git diff --check` | clean for cache scope |

## Disposable PostgreSQL qualification

The repository tool `tools/qualify_local_postgres.py` created an isolated
temporary PostgreSQL cluster below `/tmp`, exposed only by a mode-0700 Unix
socket. It required the explicit disposable confirmation, rejected external
DSNs, left `fsync=on` and `synchronous_commit=on`, recorded no secrets and
performed no production writes.

```text
metadata-store: 65 passed, 0 skipped, 0 failed
slo-service-live-postgres: 3 passed, 0 skipped, 0 failed
PostgreSQL: 17.5 (Homebrew)
CPython: 3.12.12    psycopg: 3.3.4
source revision: ea894caacf414a2676226c8297d6e5fcfd9c569b
receipt: sha256:d1d055932032e23dd0a2c181ff1bd7ca3e64847325b28792fcfa49c52fcb3503
teardown: COMPLETE
evidence class: LOCAL_EXECUTED_SELF_ATTESTED
CI / production / independent verification: NOT_RUN
```

Migration-ledger digest:
`sha256:2e97c7d985fb5a8a8345512295ffa238722b38ec30a218c582cbf2848c92f23d`

Schema-introspection digest:
`sha256:5db22f9d2b18974b3ae0d45a96848adb0a3d17e1ffe6c6657f75bb2597d8c7b4`

## Historical qualification boundaries

- An earlier consolidated non-native run recorded `1734 passed, 51 skipped,
  1 failed` in 240.22 seconds. The one failure was the unrelated,
  pre-existing `tests/test_policy_integration.py::test_sota_23_certification_refuses_without_the_rollout_evidence`
  W_TINY_LFU p95 decision-overhead budget assertion. It was not weakened or
  relabelled.
- A native-toolchain sweep was interrupted after approximately 6 minutes and
  is `NOT_RUN/INCOMPLETE`; it is not represented as a pass.
- Real provider/SDK/model calls, provider cache accounting, production
  PostgreSQL, external images, multi-host fleet, representative/holdout
  corpora, CI, independent verification and rollout remain `NOT_RUN`.
- These are engineering checks only. No result in this file certifies parity,
  production readiness or external compliance.
