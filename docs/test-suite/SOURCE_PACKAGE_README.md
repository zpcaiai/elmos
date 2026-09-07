> Provenance copy of the supplied v1.0.0 package README. It is not the current ELMOS validation report; see `IMPORT_AUDIT.md` and `VALIDATION.md`.

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
