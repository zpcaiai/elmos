# Batch 1–37 Strict Test Suite Codex Skills

This package contains 52 repository-scoped Codex test skills and 408 machine-readable seed cases covering every capability Batch 1–37. It is intentionally slightly strict: all P0/P1 cases must pass; holdout and representative workloads are mandatory where required; evidence and anti-cheating controls are enforced.

## Install

```bash
./install.sh /path/to/migration-platform
```

## Validate

```bash
python3 scripts/test-suite/validate_skill_bundle.py .
python3 scripts/test-suite/validate_test_catalog.py test-suites/batch1-37-strict/cases/catalog.json
python3 scripts/test-suite/validate_coverage_matrix.py test-suites/batch1-37-strict/coverage-matrix.json
python3 -m unittest tests/test-suite/test_toolkit.py
```

## Use with Codex

Start with `$tst-strict-suite-orchestrator`, then invoke the exact `$tst-bXX-*` skill and relevant cross-cutting skills. The authoritative release decision is produced only by `run_strict_test_gate.py`.

## Batch 1–37 strict test suite

The repository includes 52 Codex test skills and 408 machine-readable seed cases covering every Batch 1–37 capability. Start with `$tst-strict-suite-orchestrator`; the authoritative qualification command is `python3 scripts/test-suite/run_strict_test_gate.py test-suites/batch1-37-strict`. The suite fails safely until real results and immutable evidence are supplied.


# Batch 38–45 Mature Product Expansion

Added 172 Codex Skills for deployment, SRE, supply-chain security, knowledge, agents, LTS, FinOps and final mature-product certification.
