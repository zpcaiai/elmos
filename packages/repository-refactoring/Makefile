# The gate. Everything here must be green before this package is shipped.
.PHONY: check lint types test certify golden clean

PY ?= python3

check: lint types test certify

lint:
	ruff check src tests

types:
	MYPYPATH=src mypy --strict --python-version 3.11 -p elmos_repository_refactoring

test:
	$(PY) -m pytest -q tests --ignore=tests/certification

# The production certification suite: package invariants, the Golden corpus,
# and the mutation tests that prove the suite fails on a real defect.
certify:
	$(PY) -m pytest -q tests/certification

# Deliberate re-record. Never run this to make a red suite green without first
# reading the reported difference and agreeing with it.
golden:
	ELMOS_UPDATE_GOLDEN=1 $(PY) -m pytest -q tests/certification

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
