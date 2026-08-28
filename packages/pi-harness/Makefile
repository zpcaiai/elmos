PY ?= python3
PYTHONPATH := src

.PHONY: check test demo

check:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(PYTHONPATH) $(PY) -m compileall -q src

test:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(PYTHONPATH) $(PY) -m unittest discover -s tests -p 'test_*.py' -v

demo:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(PYTHONPATH) $(PY) -m elmos_pi_harness.cli demo
