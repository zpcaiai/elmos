.PHONY: install validate coverage smoke score test verify materialize clean

install:
	python3 -m pip install -e .[dev]

materialize:
	python3 scripts/materialize_cases.py

validate:
	python3 -m etgb validate

coverage:
	python3 -m etgb coverage

smoke:
	python3 -m etgb run --profile smoke --output reports/smoke-results.jsonl

score:
	python3 -m etgb score reports/smoke-results.jsonl --output reports/smoke-score.json

test:
	pytest -q

verify: validate coverage smoke score test

clean:
	rm -rf .etgb reports/*.jsonl reports/*.json reports/*.html **/__pycache__ *.egg-info
