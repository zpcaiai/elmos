JAVA_21_HOME ?= $(shell /usr/libexec/java_home -v 21 2>/dev/null)
MAVEN ?= /opt/homebrew/bin/mvn
NODE_EXECUTABLE ?= $(shell command -v node 2>/dev/null || printf '%s' '/Users/stephen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')
NODE_RUNTIME_BIN := $(dir $(NODE_EXECUTABLE))
PNPM_VERSION ?= $(shell sed -n 's/.*"packageManager": "pnpm@\([^"]*\)".*/\1/p' apps/web-console/package.json)
PNPM ?= pnpm dlx pnpm@$(PNPM_VERSION)

.PHONY: verify backend database-data infrastructure security-compliance test-quality mainframe enterprise-integration enterprise-suite mature-product-skills mature-product-packages product-roadmap production-readiness-check batch1-55-skills batch66-80-skills batch66-80-test-skills language-packs-batch81-95 batch81-95-test-skills product-batch33-38-skills product-batch33-39-skills product-batch33-55-skills product-batch40-55-skills product-batch35-38 migration-pack-admission batch27-34-skills test-suite-validate test-suite-test test-suite-check test-suite-gate test-suite-1-55-check test-suite-1-55-gate test-suite-1-65-check test-suite-1-65-gate test-suite-66-80-check test-suite-66-80-gate test-suite-81-95-check test-suite-81-95-gate test-suite-b38-45-validate test-suite-b38-45-test test-suite-b38-45-check test-suite-b38-45-gate test-suite-local-qualification dotnet python project-synthesis frontend web up down

verify: backend dotnet python frontend web
production-readiness-check: batch45-check project-synthesis web
	/opt/homebrew/bin/uv run --quiet --with pyyaml python tooling/validate_runtime_operability.py
	/opt/homebrew/bin/uv run --quiet --with pyyaml python -m unittest discover -s tests/production-readiness -p 'test_*.py'
backend:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B verify
database-data:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl engines/database-data-engine -am verify
infrastructure:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl engines/infrastructure-engine -am verify
security-compliance:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl engines/security-compliance-engine -am verify
test-quality:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl engines/test-quality-engine -am verify
mainframe:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl engines/mainframe-engine -am verify
enterprise-integration:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl engines/enterprise-integration-engine -am verify
enterprise-suite:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl engines/enterprise-suite-engine -am verify
product-roadmap:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl modules/product-roadmap-governance,apps/control-plane -am test
migration-pack-admission:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl modules/migration-pack-certification,apps/control-plane -am test
batch27-34-skills:
	python3 tooling/validate_batch27_34_integration.py
batch1-55-skills:
	/opt/homebrew/bin/uv run --quiet --with pyyaml python tooling/validate_batch1_55_skill_pack.py
	/opt/homebrew/bin/uv run --quiet --with pyyaml python tooling/ensure_runtime_skill_interfaces.py --check --root .agents/skills
	/opt/homebrew/bin/uv run --quiet --with pyyaml python tooling/ensure_runtime_skill_interfaces.py --check --root agent-skills/runtime
batch66-80-skills:
	python3 tooling/import_batch66_80_assets.py --check
	cd elmos-codex-skills-batch66-80-complete && ./validate.sh
	python3 tooling/validate_project_synthesis_integration.py
batch66-80-test-skills:
	python3 tooling/import_batch66_80_strict_test_assets.py --check
	cd elmos-codex-skills-batch66-80-slightly-strict-tests && ./validate.sh
language-packs-batch81-95:
	python3 tooling/import_batch81_95_language_packs.py --check
	cd elmos-language-packs-batch81-95-complete && ./validate.sh
	python3 tooling/validate_project_synthesis_integration.py
batch81-95-test-skills:
	python3 tooling/import_batch81_95_strict_test_assets.py --check
	cd elmos-batch81-95-slightly-strict-test-skills && ./validate.sh
product-batch33-38-skills: product-batch33-39-skills
product-batch33-39-skills: product-batch33-55-skills
product-batch40-55-skills: product-batch33-55-skills
product-batch33-55-skills:
	/opt/homebrew/bin/uv run --quiet --with pyyaml python tooling/validate_product_batch33_55_integration.py
	/opt/homebrew/bin/uv run --quiet --with pyyaml python tooling/ensure_runtime_skill_interfaces.py --check
product-batch35-38: product-batch33-38-skills
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl modules/source-control-workspace-governance,modules/secure-execution-plane,modules/evidence-assurance-fabric,modules/continuous-authorization,modules/persistence,apps/control-plane -am test
mature-product-skills: b29-skills-test b30-skills-test b31-skills-test batch32-check batch33-check batch34-check batch35-check batch36-check batch37-check batch38-check batch39-check batch40-check batch41-check batch42-check batch43-check batch44-check batch45-check
	/opt/homebrew/bin/uv run --quiet --with jsonschema --with pyyaml python scripts/validate_mature_product_series.py
	/opt/homebrew/bin/uv run --quiet --with 'jsonschema>=4.23' --with pyyaml python -m unittest discover -s tests -p 'mature_product_gate_test.py'
mature-product-packages:
	python3 scripts/package_mature_product_series.py
test-suite-validate:
	/opt/homebrew/bin/uv run --quiet --with pyyaml python scripts/test-suite/validate_skill_bundle.py .
	python3 scripts/test-suite/validate_test_catalog.py test-suites/batch1-37-strict/cases/catalog.json
	python3 scripts/test-suite/validate_coverage_matrix.py test-suites/batch1-37-strict/coverage-matrix.json
	/opt/homebrew/bin/uv run --quiet --with 'jsonschema>=4.23' python scripts/test-suite/validate_schema_bundle.py
	python3 scripts/test-suite/generate_integration_manifest.py --check
	python3 scripts/test-suite/validate_batch1_55_slightly_strict.py
	python3 scripts/test-suite/validate_batch1_65_slightly_strict.py
	python3 tooling/import_batch66_80_strict_test_assets.py --check
	cd elmos-codex-skills-batch66-80-slightly-strict-tests && ./validate.sh
	python3 scripts/test-suite/validate_batch66_80_slightly_strict.py
	python3 tooling/import_batch81_95_strict_test_assets.py --check
	cd elmos-batch81-95-slightly-strict-test-skills && ./validate.sh
	python3 scripts/test-suite/validate_batch81_95_language_packs.py
test-suite-test:
	python3 -m unittest discover -s tests/test-suite -p 'test_*.py'
test-suite-check: test-suite-validate test-suite-test test-suite-b38-45-check
test-suite-gate:
	python3 scripts/test-suite/run_strict_test_gate.py test-suites/batch1-37-strict
test-suite-1-55-check:
	python3 scripts/test-suite/validate_batch1_55_slightly_strict.py
	python3 -m unittest tests/test-suite/test_batch1_55_supplemental.py
test-suite-1-55-gate:
	python3 scripts/test-suite/run_batch1_55_slightly_strict_gate.py test-suites/batch1-55-slightly-strict
test-suite-1-65-check:
	python3 scripts/test-suite/validate_batch1_65_slightly_strict.py
	python3 -m unittest tests/test-suite/test_batch1_65_supplemental.py
test-suite-1-65-gate:
	python3 scripts/test-suite/run_batch1_65_slightly_strict_gate.py test-suites/batch1-65-slightly-strict
test-suite-66-80-check: batch66-80-test-skills
	python3 scripts/test-suite/validate_batch66_80_slightly_strict.py
	python3 -m unittest tests/test-suite/test_batch66_80_supplemental.py
test-suite-66-80-gate:
	python3 scripts/test-suite/run_batch66_80_slightly_strict_gate.py test-suites/batch66-80-slightly-strict
test-suite-81-95-check: batch81-95-test-skills
	python3 scripts/test-suite/validate_batch81_95_language_packs.py
	python3 -m unittest tests/test-suite/test_batch81_95_language_packs.py
test-suite-81-95-gate: batch81-95-test-skills
	python3 scripts/test-suite/run_batch81_95_language_pack_gate.py test-suites/batch81-95-language-packs-slightly-strict
test-suite-b38-45-validate:
	python3 scripts/test-suite-b38-45/validate_skill_bundle.py .
	python3 scripts/test-suite-b38-45/validate_test_catalog.py test-suites/batch38-45-strict/cases/catalog.json
	python3 scripts/test-suite-b38-45/validate_coverage_matrix.py test-suites/batch38-45-strict/coverage-matrix.json
	/opt/homebrew/bin/uv run --quiet --with 'jsonschema>=4.23' python scripts/test-suite-b38-45/validate_schema_bundle.py
	python3 scripts/test-suite-b38-45/generate_control_manifest.py --check
test-suite-b38-45-test:
	python3 -m unittest tests/test-suite-b38-45/test_toolkit.py
test-suite-b38-45-check: test-suite-b38-45-validate test-suite-b38-45-test
test-suite-b38-45-gate:
	python3 scripts/test-suite-b38-45/run_strict_gate.py test-suites/batch38-45-strict
test-suite-local-qualification:
	test -n "$(TEST_SUITE_EVIDENCE_DIR)" || { echo 'Set TEST_SUITE_EVIDENCE_DIR to a new immutable output directory'; exit 2; }
	python3 scripts/test-suite/run_repository_qualification.py --output "$(TEST_SUITE_EVIDENCE_DIR)"
dotnet:
	PATH="/opt/homebrew/bin:$$PATH" dotnet test engines/dotnet-engine/Elmos.Dotnet.slnx
python:
	/opt/homebrew/bin/uv --directory engines/python-engine run --locked pytest
	/opt/homebrew/bin/uv --directory engines/python-engine run --locked ruff check src tests
	/opt/homebrew/bin/uv --directory engines/python-engine run --locked mypy src
project-synthesis:
	python3 tooling/validate_project_synthesis_integration.py
	/opt/homebrew/bin/uv run --quiet --with 'jsonschema>=4.23' python tooling/validate_project_synthesis_batch61_65_schemas.py
	/opt/homebrew/bin/uv --directory engines/project-synthesis-engine run --locked pytest
	/opt/homebrew/bin/uv --directory engines/project-synthesis-engine run --locked ruff check src tests scripts
	/opt/homebrew/bin/uv --directory engines/project-synthesis-engine run --locked mypy src
	/opt/homebrew/bin/uv --directory engines/project-synthesis-engine run --locked python scripts/run_acceptance.py
frontend:
	CI=true PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir engines/frontend-client-engine install --frozen-lockfile
	PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir engines/frontend-client-engine check
web:
	CI=true PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir apps/web-console install --frozen-lockfile
	PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir apps/web-console check
up:
	docker compose -f deploy/compose/docker-compose.yml up --build
down:
	docker compose -f deploy/compose/docker-compose.yml down

include Makefile.batch29
include Makefile.batch30
include Makefile.batch31
include Makefile.batch32
include Makefile.batch33
include Makefile.batch34
include Makefile.batch35
include Makefile.batch36
include Makefile.batch37
include Makefile.batch38
include Makefile.batch39
include Makefile.batch40
include Makefile.batch41
include Makefile.batch42
include Makefile.batch43
include Makefile.batch44
include Makefile.batch45
