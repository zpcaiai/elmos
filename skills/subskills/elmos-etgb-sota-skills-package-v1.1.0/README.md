# Elmos ETGB SOTA Skills Package v1.1.0

**ETGB — Elmos Enterprise Transformation & Generation Benchmark** is the executable testing, control and release-certification package for four Elmos business lines:

1. Spring legacy modernization;
2. whole-repository cross-language conversion;
3. multilingual project generation;
4. SQL dialect and SQL routine conversion.

v1.1.0 turns the original benchmark package into a production integration contract. It contains:

- **46,664 materialized cases** across the four domains and 100 cross-cutting operational scenarios;
- **24 composable `SKILL.md` Skills**;
- executable CLI, local adapters, Oracle, scoring, risk planning, candidate freezing and statistical utilities;
- durable state, checkpoint, evidence, budget and policy reference implementations;
- PostgreSQL schema and RLS, Harness adapter contract, OpenAPI, AsyncAPI and OTel conventions;
- fixed-corpus governance, hidden-test separation, supply-chain checks and release gates;
- offline smoke fixtures and unit tests.

> “Full coverage” means 100% of the declared ETGB v1.1 capability-cell model in `matrices/coverage-requirements.yaml`; it does not claim to cover future languages, frameworks or DBMS features not yet declared.

## Package layout

```text
skills/          24 Agent/Skill execution contracts
matrices/        domain and cross-cutting capability matrices
suites/          46,664 concrete JSONL cases, index and summary
schemas/         case/result/candidate/plan/policy/checkpoint/evidence schemas
etgb/            executable CLI and reference control-plane modules
integrations/    PostgreSQL, Harness, OpenAPI, AsyncAPI, OTel, policy, Temporal
fixtures/        four completely offline smoke fixtures
docs/            SOTA plan, production runtime, security, recovery and integration
corpora/         pinned public corpus metadata and review status
```

## Verify the package

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
make verify
```

Equivalent commands:

```bash
etgb validate
etgb skills-audit
etgb coverage
etgb run --profile smoke --output reports/smoke-results.jsonl
etgb score reports/smoke-results.jsonl --output reports/smoke-score.json
pytest -q
```

## Production workflow

```bash
# 1. Freeze an immutable model/Prompt/Skill/rule/toolchain candidate
etgb freeze-candidate examples/release-candidate.yaml \
  --output reports/release-candidate.json

# 2. Create a risk-based immutable plan and stable shards
etgb plan --changed-from origin/main --max-cases 500 --shards 8 \
  --candidate-digest sha256:... --output reports/pr-plan.json

# 3. Estimate Elmos machine wall-clock/tokens/credits
etgb eta reports/pr-plan.json --history reports/history.jsonl --concurrency 3

# 4. Execute, score, triage and certify
etgb run --plan reports/pr-plan.json --output reports/results.jsonl --allow-unavailable
etgb score reports/results.jsonl --output reports/score.json
etgb triage reports/results.jsonl --output reports/failure-clusters.json
etgb gate reports/score.json --output reports/gate-decision.json
```

The included local Runner executes only reference adapters. Real repository/DB cases intentionally remain `unavailable` until Elmos implements `integrations/harness/adapter-contract.yaml` with its sandbox, database and provider infrastructure.

## Hard principles

- build success is not semantic equivalence;
- raw behavior, state, side effects, transactions and security decisions are compared;
- P0 SSER, data corruption, privilege expansion and authority bypass are zero-tolerance;
- candidate, plan, corpus, Environment, Oracle and evidence are immutable/digested;
- hidden tests are isolated from generation/translation workers;
- every side effect and charge is idempotent and fenced;
- pause/resume validates checkpoints rather than restarting blindly;
- per-account active task concurrency defaults to three;
- machine ETA excludes human engineering time;
- no score is certifiable without sealed evidence and complete release metrics.

Start with `docs/SOTA_TEST_PLAN.md`, `docs/PRODUCTION_RUNTIME.md`, `docs/ELMOS_INTEGRATION.md` and `skills/manifest.yaml`.
