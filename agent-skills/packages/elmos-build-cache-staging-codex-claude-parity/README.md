# ELMOS Build Cache, File Staging, and Codex/Claude-Class Cache Parity Skills

Version **1.2.0** — 2026-08-20

This package upgrades v1.1.0 from deterministic build/artifact caching plus SOTA adaptive policies to a full coding-agent cache architecture. It retains all 31 previous Skills and adds 11 parity Skills, for **42 executable Skills**.

The objective is to reach or approach Codex/Claude Code class cache behavior on declared warm workloads: same project, stable provider/model/effort/tool profile, follow-up turns, small edits, exact reruns, unchanged environments, and restart recovery.

This package defines implementation contracts and certification gates. It does not claim the production ELMOS repository already achieves the fixture values. An achieved claim requires a fresh report bound to source, configuration, provider profiles, corpus, and platform.

## Mandatory parity gates

- stable-turn eligible cached-token reuse after turn 3: **>= 90%**;
- unexpected full-prefix miss: **<= 2%**;
- exact-rerun compute-weighted Action reuse: **>= 99%** and zero redundant validated model/compiler/test calls;
- <=1% edit with unchanged public interfaces: **>= 90%** weighted reuse;
- implementation-only unnecessary invalidation: **<= 5%**;
- unchanged-environment snapshot hit: **>= 95%**;
- warm-start p95 reduction: **>= 80%**;
- restart sealed-artifact reuse: **>= 99.9%**;
- stable follow-up net wall-clock saving: **>= 70%**;
- model input cost saving: **>= 80%**;
- accepted false/cross-tenant/corrupt/under-validated hits: **0**.

## New parity Skills

1. `elmos-provider-prompt-cache-adapters`
2. `elmos-canonical-prompt-prefix-layout`
3. `elmos-append-only-repository-context-ledger`
4. `elmos-cache-preserving-context-compaction`
5. `elmos-environment-snapshot-cache`
6. `elmos-cache-affinity-routing`
7. `elmos-multi-layer-cache-coordinator`
8. `elmos-cache-miss-diagnostics`
9. `elmos-codex-claude-parity-benchmark`
10. `elmos-cache-hit-slo-autotuning`
11. `elmos-codex-claude-cache-parity-rollout`

The entry Skill is `elmos-codex-claude-cache-parity-rollout`.

## Architecture

```text
canonical prompt prefix + provider adapters
append-only repository context + planned compaction
exact Action Cache + CAS + incremental DAG
environment snapshots + native build caches
provider/model/worker/shard affinity
multi-layer coordinator + singleflight
first-difference miss diagnostics
parity benchmark + SLO autotuning + rollback
```

Prompt-prefix reuse is not exact model-output reuse. Provider prompt caches, semantic candidates, and learned policies never bypass ActionKey, digest, tenancy, provenance, validation level, staged-file lifecycle, or atomic publication.

## Validate and install

```bash
./validate.sh
./install.sh --all
```

Custom destination:

```bash
./install.sh --dest /path/to/skills
```

Overwrite a previous package only when explicit:

```bash
./install.sh --all --overwrite
```

Evaluate the illustrative parity fixture:

```bash
python3 scripts/run_cache_parity_benchmark.py \
  examples/cache-parity-observations.example.json
```

See `README.zh-CN.md`, `PACKAGE_INDEX.md`, `AGENTS.md`, `docs/source-packages/elmos-codex-claude-cache-parity-spec.md`, and `tests/acceptance/codex-claude-cache-parity-matrix.md` before implementation.
