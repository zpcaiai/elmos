.PHONY: validate test gate
validate:
	./validate.sh
test:
	python3 -m unittest discover -s tests -v
gate:
	python3 scripts/test-suite-b66-80/run_slightly_strict_gate.py test-suites/batch66-80-slightly-strict
