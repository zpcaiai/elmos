PY ?= python3
MYPY ?= mypy
PYTHONPATH := src

.PHONY: check test typecheck demo qualification

check:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(PYTHONPATH) $(PY) -m compileall -q src

test:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(PYTHONPATH) $(PY) -m unittest discover -s tests -p 'test_*.py' -v

typecheck:
	PYTHONDONTWRITEBYTECODE=1 MYPYPATH=$(PYTHONPATH) $(MYPY)

demo:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(PYTHONPATH) $(PY) -m elmos_pi_harness.cli demo

qualification:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(PYTHONPATH) $(PY) -m elmos_pi_harness.cli qualification-status
