.PHONY: install materialize validate release-validate coverage feature-coverage surface-audit skills-audit smoke test evidence manifest verify

install:
	python3 -m pip install -e '.[dev]'

materialize:
	python3 -m etgb materialize

validate:
	python3 -m etgb validate

release-validate:
	python3 -m etgb validate --release

coverage:
	python3 -m etgb coverage

feature-coverage:
	python3 -m etgb feature-coverage --output reports/FEATURE_COVERAGE.json

surface-audit:
	python3 -m etgb surface-audit examples/product-surface.yaml --output reports/SURFACE_AUDIT.json

skills-audit:
	python3 -m etgb skills-audit

smoke:
	./scripts/run_smoke.sh

test:
	pytest -q

evidence:
	python3 scripts/create_evidence_bundle.py

manifest:
	python3 scripts/generate_package_manifest.py

verify:
	./scripts/verify_package.sh
