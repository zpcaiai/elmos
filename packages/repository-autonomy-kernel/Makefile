.PHONY: test check

UV ?= uv
RUFF ?= ruff

test:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src $(UV) run --no-project --quiet --with pytest python -m pytest -q -p no:cacheprovider

check: test
	PYTHONDONTWRITEBYTECODE=1 $(RUFF) check src tests
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m compileall -q src
