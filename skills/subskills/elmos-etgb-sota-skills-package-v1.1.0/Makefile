.PHONY: install materialize validate release-validate coverage skills-audit smoke test evidence manifest verify

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
