.PHONY: test check

UV ?= uv

test:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src $(UV) run --no-project --quiet --with pytest python -m pytest -q -p no:cacheprovider

check: test
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with ruff ruff check src tests
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m compileall -q src
