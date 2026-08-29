JAVA_21_HOME ?= $(shell if [ -x /usr/libexec/java_home ]; then /usr/libexec/java_home -v 21 2>/dev/null; else printf '%s' "$$JAVA_HOME"; fi)
MAVEN ?= mvn
UV ?= uv
DOTNET ?= dotnet
# Homebrew installs the .NET SDK outside the default PATH on macOS. Prepending a
# directory that does not exist is harmless everywhere else, and both this and
# DOTNET stay overridable so no machine-specific layout is baked in.
DOTNET_PATH_PREFIX ?= /opt/homebrew/bin
# Resolve node from PATH. Set NODE_EXECUTABLE explicitly to pin a specific
# runtime; the previous default hard-coded one developer's home directory, which
# resolved to nothing on every other machine and silently prefixed PATH with a
# non-existent directory instead of reporting the missing toolchain.
NODE_EXECUTABLE ?= $(shell command -v node 2>/dev/null)
# Never expands to the empty string: an empty PATH element means the current
# directory, which would let a checked-out repository shadow real tools. When
# node is absent this stays a path that cannot exist, PATH resolution falls
# through, and the recipe fails with a plain "node: command not found".
NODE_RUNTIME_BIN := $(if $(NODE_EXECUTABLE),$(dir $(NODE_EXECUTABLE)),/nonexistent/node-runtime-not-found/)
PNPM_VERSION ?= $(shell sed -n 's/.*"packageManager": "pnpm@\([^"]*\)".*/\1/p' apps/web-console/package.json)
PNPM ?= pnpm dlx pnpm@$(PNPM_VERSION)
PROFILE ?= synthesis
RUNTIME_STATUS_OUTPUT ?= .elmos/toolchains/runtime-status.json

.PHONY: verify backend-fast business-line-contracts makefile-portability-check model-catalog-check backend database-data infrastructure security-compliance test-quality mainframe enterprise-integration enterprise-suite mature-product-skills mature-product-toolchain-test mature-product-packages product-roadmap production-readiness-check precision-migration-b01-44-skills precision-migration-b01-44-check precision-migration-b01-44-qualification chinadb-commercial-migration-skills batch1-55-skills batch66-80-skills batch66-80-test-skills language-packs-batch81-95 batch81-95-test-skills batch97-104-skills product-batch56-skills product-closure-convergence-skills product-closure-gate product-convergence-gate product-batch33-38-skills product-batch33-39-skills product-batch33-55-skills product-batch40-55-skills product-batch35-38 migration-pack-admission batch27-34-skills production-runtime production-runtime-local test-suite-validate test-suite-test test-suite-check test-suite-gate test-suite-1-55-check test-suite-1-55-gate test-suite-1-65-check test-suite-1-65-gate test-suite-66-80-check test-suite-66-80-gate test-suite-81-95-check test-suite-81-95-gate test-suite-b38-45-validate test-suite-b38-45-test test-suite-b38-45-check test-suite-b38-45-gate test-suite-local-qualification toolchains-validate toolchains-doctor toolchains-check toolchains-install toolchains-env dotnet python project-synthesis project-synthesis-toolchains frontend sql-transpiler sql-dialect component-dialect web up down local-commercial-up local-commercial-smoke local-commercial-status local-commercial-down operations-scripts-test test-suite-certification-rehearsal repository-autonomy-kernel openhands-absorption ai-capability-enhancement-skills functional-assurance-skills knowledge-skill-model-foundry-skills pricing-billing-skills commercial-capability-expansion-skills semantic-assurance-expansion-skills polyglot-semantic-assurance-skills

.PHONY: frt-g01-g30-skills frt-g01-g30-check

verify: business-line-contracts backend dotnet python frontend sql-transpiler sql-dialect component-dialect web
business-line-contracts: model-catalog-check makefile-portability-check chinadb-commercial-migration-skills
	python3 scripts/operations/validate_spring_route_contract.py
	python3 scripts/operations/validate_translation_route_matrix.py
makefile-portability-check:
	python3 scripts/operations/validate_makefile_portability.py
model-catalog-check:
	python3 scripts/operations/validate_model_catalog.py
production-readiness-check: business-line-contracts chinadb-commercial-migration-skills sql-transpiler batch45-check project-synthesis batch97-104-skills product-batch56-skills product-closure-convergence-skills web operations-scripts-test
	$(UV) run --quiet --with pyyaml python tooling/validate_runtime_operability.py
	$(UV) run --quiet --with pyyaml python -m unittest discover -s tests/production-readiness -p 'test_*.py'
# The modernization-proof release scripts carry their unit tests next to the code
# they cover, and nothing ran them: they are under scripts/, so neither the
# tests/ discovery roots nor any CI job reached them, and ~900 lines of coverage
# could rot without ever going red. Discovery starts at scripts/operations rather
# than the repository root because those tests insert their own directory on
# sys.path and import their subjects by bare module name; scripts/operations is
# not a package, so `-t .` cannot find it.
operations-scripts-test:
	$(UV) run --quiet --with pyyaml python -m unittest discover -s scripts/operations -p 'test_*.py'
.PHONY: pi-harness
pi-harness:
	PYTHONDONTWRITEBYTECODE=1 python3 tooling/integrate_pi_harness.py --check
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/pi-harness/src python3 -m unittest discover -s packages/pi-harness/tests -p 'test_*.py'
backend:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B verify
# Seven modules form a closed cluster that no `apps/` component references:
# intake -> semantic -> uir -> skeleton -> lowering -> dependency-migration ->
# framework-migration. docs/BUSINESS_LINE_CLOSURE_MATRIX.md records five of them;
# the two migration modules belong to the same dead chain. They are still built
# and tested on every `make backend`, so they cost build time on a path no
# product request reaches.
#
# They cannot simply be dropped from <modules>: ArchitectureRulesTest asserts
# ArchUnit boundary rules over `io.elmos.intake..` through
# `io.elmos.frameworkmigration..`, and those rules would silently analyse an
# empty class set. Removing the cluster therefore has to retire the matching
# rules in the same change, and that has to be verified by a real `make backend`.
# Until then this target skips the cluster for local iteration only; `verify`
# and CI keep building everything.
LEGACY_LOWERING_CHAIN := !modules/intake,!modules/semantic,!modules/uir,!modules/skeleton,!modules/lowering,!modules/dependency-migration,!modules/framework-migration,!modules/architecture-tests
backend-fast:
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl '$(LEGACY_LOWERING_CHAIN)' verify
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

production-runtime:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 python scripts/production-runtime/validate_package.py
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/production-runtime/validate_implementation.py
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/production-runtime -p 'test_*.py'
	helm lint deploy/helm/elmos-runtime --strict
	helm lint deploy/helm/elmos-runtime --strict --values tests/production-runtime/helm-production-values.yaml
	helm template qualification deploy/helm/elmos-runtime --values tests/production-runtime/helm-production-values.yaml >/dev/null
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl modules/production-runtime,apps/production-runtime-control-plane,apps/production-runtime-worker -am test

production-runtime-local:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/production-runtime/run_local_harness.py
.PHONY: repository-migration-platform-skills
repository-migration-platform-skills:
	cd skills/repository-migration-platform-skills-batch1-38 && ./validate.sh
.PHONY: large-repository-database-design-skills
large-repository-database-design-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 python tooling/integrate_large_repository_database_design.py --check
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 python -m unittest discover -s tests/large-repository-database-design -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 python3 skills/elmos-large-repository-database-design-v1.0.0/scripts/validate_database_design.py
	bash -n scripts/large_repository_database_design/run_postgres_validation.sh
precision-migration-b01-44-skills:
	python3 tooling/generate_precision_migration_handlers.py --check
	python3 tooling/generate_precision_migration_external_profiles.py --check
	python3 tooling/generate_precision_migration_external_engineering_cases.py --check
	$(UV) run --quiet --with pyyaml --with jsonschema python scripts/precision_migration/validate_platform.py
precision-migration-b01-44-check: precision-migration-b01-44-skills
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/precision-migration -p 'test_*.py'
	python3 -m scripts.precision_migration.qualify_contracts --check
	python3 -m scripts.precision_migration.qualify_domains --check
	python3 -m scripts.precision_migration.qualify_orchestrators --check
	python3 -m scripts.precision_migration.qualify_b41 --check
	python3 -m scripts.precision_migration.qualify_specialized --check
	python3 -m scripts.precision_migration.qualify_external_engineering --check
	python3 -m scripts.precision_migration.validate_b16_routes
	python3 -m scripts.precision_migration.qualify_b16 --check
	python3 -m scripts.precision_migration.build_coverage --check
	python3 -m scripts.precision_migration.external validate-profiles
	python3 -m scripts.precision_migration.run_production_code_gate --check
	$(UV) run --quiet --with jsonschema python scripts/batch35/validate_verification_pack.py verification-packs/precision-migration-b01-44-runtime
	$(UV) run --quiet --with jsonschema python scripts/batch35/run_verification_gate.py verification-packs/precision-migration-b01-44-runtime
precision-migration-b01-44-qualification: precision-migration-b01-44-check
	python3 -m scripts.precision_migration.run_local_qualification
chinadb-commercial-migration-skills:
	cd skills/chinadb-commercial-migration-skills-v1.0.0 && PYTHONDONTWRITEBYTECODE=1 python3 validators/validate_package.py
	cd skills/chinadb-commercial-migration-skills-v1.0.0 && shasum -a 256 -c CHECKSUMS.sha256
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml python tooling/integrate_chinadb_commercial_migration_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml python -m unittest discover -s tests/chinadb-commercial-migration -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with jsonschema==4.25.1 python -m unittest discover -s tests/chinadb-sql-extension-schema -p 'test_*.py'
	$(UV) --directory engines/database-data-engine/sql-transpiler run --locked pytest tests/test_skill_runtime.py tests/test_http_api.py tests/test_production_qualification.py
	$(UV) --directory engines/database-data-engine/sql-transpiler run --locked ruff check src tests
	$(UV) --directory engines/database-data-engine/sql-transpiler run --locked mypy src
.PHONY: database-bigdata-skills
database-bigdata-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_database_bigdata_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s tests/database-bigdata-skills -p 'test_*.py'
.PHONY: project-intelligence-skills
project-intelligence-skills:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/project-intelligence-engine/src python3 -m unittest discover -s engines/project-intelligence-engine/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/project-intelligence-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/qualify_project_intelligence_runtime.py --check
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_project_intelligence_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s tests/project-intelligence-skills -p 'test_*.py'
.PHONY: legacy-web-modernization-skills
legacy-web-modernization-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_legacy_web_modernization_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/legacy-web-modernization-engine/src python3 -m unittest discover -s engines/legacy-web-modernization-engine/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/legacy-web-modernization-engine/src python3 -m elmos_legacy_web_modernization.cli validate
.PHONY: autonomous-qa-self-healing-skills
autonomous-qa-self-healing-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_autonomous_qa_self_healing_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s tests/autonomous-qa-self-healing -p 'test_*.py'
.PHONY: ai-capability-enhancement-skills
ai-capability-enhancement-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_ai_capability_enhancement_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/ai-capability-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s engines/ai-capability-engine/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/ai-capability-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s tests/ai-capability-enhancement -p 'test_*.py'
	cd skills/elmos-ai-capability-enhancement-skills-v4.1.0 && PYTHONPATH=. $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s tests -p 'test_*.py'

.PHONY: knowledge-skill-model-foundry-skills
knowledge-skill-model-foundry-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_knowledge_skill_model_foundry_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/knowledge-skill-model-foundry-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s engines/knowledge-skill-model-foundry-engine/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/knowledge-skill-model-foundry-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s tests/knowledge-skill-model-foundry-skills -p 'test_*.py'

.PHONY: pricing-billing-skills
pricing-billing-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet python tooling/integrate_pricing_billing_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/pricing-billing-engine/src $(UV) run --quiet python -m unittest discover -s engines/pricing-billing-engine/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/pricing-billing-engine/src $(UV) run --quiet python -m unittest discover -s tests/pricing-billing-skills -p 'test_*.py'

.PHONY: commercial-capability-expansion-skills
commercial-capability-expansion-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_commercial_capability_expansion_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/commercial-capability-expansion-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with pytest python -m pytest tests/commercial-capability-expansion-skills/ -v

.PHONY: semantic-assurance-expansion-skills
semantic-assurance-expansion-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_semantic_assurance_expansion_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/semantic-assurance-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with pytest python -m pytest tests/semantic-assurance-expansion-skills/ -v

.PHONY: polyglot-semantic-assurance-skills
polyglot-semantic-assurance-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_polyglot_semantic_assurance_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/polyglot-semantic-compiler-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with pytest python -m pytest tests/polyglot-semantic-assurance-skills/ -v

.PHONY: unified-cli-gateway
unified-cli-gateway:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/unified-cli-gateway/src:engines/polyglot-semantic-compiler-engine/src:engines/commercial-capability-expansion-engine/src:engines/semantic-assurance-engine/src:engines/knowledge-skill-model-foundry-engine/src:engines/build-cache-engine/src:engines/formal-assurance-engine/src:engines/autonomous-qa-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with pytest python -m pytest tests/unified-cli-gateway/ -v





.PHONY: formal-assurance-kernel
formal-assurance-kernel:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_formal_assurance_kernel.py --check
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with ruff==0.15.20 ruff check engines/formal-assurance-engine/src engines/formal-assurance-engine/tests
	MYPY_CACHE_DIR=/tmp/elmos-formal-assurance-mypy PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with mypy==2.1.0 mypy --ignore-missing-imports engines/formal-assurance-engine/src/elmos_formal_assurance
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/formal-assurance-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s engines/formal-assurance-engine/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/formal-assurance-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s tests/formal-assurance-kernel -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 python scripts/formal_assurance/generate_local_qualification.py --check
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with jsonschema==4.25.1 python scripts/batch35/validate_verification_pack.py verification-packs/formal-assurance-kernel-local
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with jsonschema==4.25.1 python scripts/batch35/run_verification_gate.py verification-packs/formal-assurance-kernel-local

.PHONY: formal-assurance-kernel-qualify
formal-assurance-kernel-qualify:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/formal-assurance-engine/src $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python scripts/formal_assurance/generate_local_qualification.py

repository-autonomy-kernel:
	PYTHONDONTWRITEBYTECODE=1 python3 tooling/validate_repository_autonomy_kernel.py
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/repository-autonomy-kernel/src $(UV) run --no-project --quiet --with pytest python -m pytest -q -p no:cacheprovider packages/repository-autonomy-kernel/tests
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with ruff ruff check packages/repository-autonomy-kernel/src packages/repository-autonomy-kernel/tests tooling/validate_repository_autonomy_kernel.py
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/repository-autonomy-kernel/src python3 -m compileall -q packages/repository-autonomy-kernel/src

openhands-absorption:
	PYTHONDONTWRITEBYTECODE=1 python3 engines/openhands-absorption-engine/tools/validate_engine.py
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/openhands-absorption-engine/src python3 -m unittest discover -s engines/openhands-absorption-engine/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/openhands-absorption-engine/src python3 -m elmos_openhands validate

.PHONY: frontend-to-miniapp-skills
frontend-to-miniapp-skills:
	@set -eu; \
	closeout() { \
		status=$$?; \
		trap - EXIT HUP INT TERM; \
		set +e; \
		PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_frontend_to_miniapp_skills.py --closeout-portable; \
		closeout_status=$$?; \
		set -e; \
		if [ "$$status" -ne 0 ]; then exit "$$status"; fi; \
		exit "$$closeout_status"; \
	}; \
	trap closeout EXIT; \
	trap 'exit 129' HUP; \
	trap 'exit 130' INT; \
	trap 'exit 143' TERM; \
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_frontend_to_miniapp_skills.py --qualify-local; \
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_frontend_to_miniapp_skills.py --refresh-owned; \
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_frontend_to_miniapp_skills.py --check; \
	node client-packs/frontend-to-miniapp-vue3-wechat-v1/certification/replay-local-runtime.mjs --check; \
	python3 scripts/batch32/run_client_gate.py client-packs/frontend-to-miniapp-vue3-wechat-v1

.PHONY: multimodal-intake-skills
multimodal-intake-skills:
	PYTHONDONTWRITEBYTECODE=1 python3 tooling/integrate_multimodal_intake_skills.py --write
	PYTHONDONTWRITEBYTECODE=1 python3 tooling/integrate_multimodal_intake_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/multimodal-intake-engine/src python3 engines/multimodal-intake-engine/tools/render_operation_input_schema.py --check
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pytest==8.4.1 python -m pytest -q -p no:cacheprovider tests/multimodal-intake/test_integration.py
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/multimodal-intake-engine/src $(UV) run --quiet --with pytest==8.4.1 python -m pytest -q -p no:cacheprovider engines/multimodal-intake-engine/tests
	PYTHONDONTWRITEBYTECODE=1 python3 engines/multimodal-intake-engine/tools/verify_sdks.py --check
	PATH="$(NODE_RUNTIME_BIN):$$PATH" node apps/web-console/app/lib/server/multimodalIntakeRunner.verify.mjs
	PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir apps/web-console exec tsc --noEmit
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with jsonschema==4.25.1 python scripts/batch35/validate_verification_pack.py verification-packs/multimodal-intake-authorization-v1
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with jsonschema==4.25.1 python scripts/batch35/run_verification_gate.py verification-packs/multimodal-intake-authorization-v1
.PHONY: build-cache-staging-parity-skills
build-cache-staging-parity-skills:
	PYTHONDONTWRITEBYTECODE=1 python3 tooling/import_build_cache_parity_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/build-cache-staging-parity -p 'test_*.py'
.PHONY: repository-task-router-skills
repository-task-router-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_repository_task_router_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/repository-orchestrator/src python3 -m unittest discover -s packages/repository-orchestrator/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s tests/repository-task-router-skills -p 'test_*.py'
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl modules/repair-orchestration,apps/agent-gateway -am test
	PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir apps/web-console exec tsc --noEmit
	PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir apps/web-console exec playwright test e2e/repository-orchestrator.spec.ts --project=chromium
modernization-b01-44-packages:
	PYTHONDONTWRITEBYTECODE=1 python3 -m scripts.modernization_b01_44.cli packages --summary
modernization-b01-44-foundation:
	PYTHONDONTWRITEBYTECODE=1 python3 -m scripts.modernization_b01_44.generate_foundation --check
modernization-b01-44-test: modernization-b01-44-packages modernization-b01-44-foundation
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/modernization-b01-44 -p 'test_*.py'
modernization-b01-44-mutation:
	PYTHONDONTWRITEBYTECODE=1 python3 -m scripts.modernization_b01_44.mutation_check
modernization-b01-44-run:
	PYTHONDONTWRITEBYTECODE=1 python3 -m scripts.modernization_b01_44.cli run --batches 1-44 --scope svc-a
modernization-b01-44-gate: modernization-b01-44-test modernization-b01-44-mutation
	@echo "modernization B01-44: packages verified, suite green, mutations killed"
batch27-34-skills:
	python3 tooling/validate_batch27_34_integration.py
frt-g01-g30-skills:
	python3 skills/FRT_G01_G30_Complete_Skills_Pack/scripts/validate_package.py
	python3 tooling/integrate_frt_g01_g30.py --check
	python3 scripts/frt/validate_frt_platform.py
frt-g01-g30-check: frt-g01-g30-skills frontend
	CI=true PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir apps/web-console install --frozen-lockfile
	PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir apps/web-console check
# Optional canonical Skill import bundles.
#
# A normal source checkout intentionally does not contain them; the rule is
# stated in tooling/validate_batch97_104_installed.py.  Their byte identities
# live in the tracked installed manifests under docs/*/installed-manifest.json,
# so a checkout validates the installed distribution, not the absent bundle.
#
# Every guarded step below therefore runs only when its bundle is present.  When
# it is absent, tooling/source_package_guard.py prints one loud, greppable
# SOURCE_PACKAGE_ABSENT= line and the target continues with whatever real gate
# does not need the bundle.  A skipped bundle-integrity check must never be
# readable as a passed one, which is why the marker is printed rather than
# swallowed.  Use `make <target> REQUIRE_SOURCE_PACKAGES=1` to demand the
# bundles instead (release and bundle-publishing runs should).
SOURCE_PACKAGE_GUARD := python3 tooling/source_package_guard.py
REQUIRE_SOURCE_PACKAGES ?=
ifeq ($(REQUIRE_SOURCE_PACKAGES),)
PROJECT_SYNTHESIS_INTEGRATION_FLAGS :=
else
PROJECT_SYNTHESIS_INTEGRATION_FLAGS := --require-packages
endif

# $(call guarded,<package dir>,<manifest file>,<shell command run when present>)
ifeq ($(REQUIRE_SOURCE_PACKAGES),)
guarded = @if $(SOURCE_PACKAGE_GUARD) $(1) --manifest $(2); then set -e; $(3); fi
else
guarded = @$(SOURCE_PACKAGE_GUARD) $(1) --manifest $(2) && set -e && $(3)
endif

batch1-55-skills:
	$(call guarded,elmos-codex-skills-batch1-55-complete,manifest.json,\
		$(UV) run --quiet --with pyyaml python tooling/validate_batch1_55_skill_pack.py)
	$(UV) run --quiet --with pyyaml python tooling/ensure_runtime_skill_interfaces.py --check --root .agents/skills
	$(UV) run --quiet --with pyyaml python tooling/ensure_runtime_skill_interfaces.py --check --root agent-skills/runtime
batch66-80-skills:
	$(call guarded,elmos-codex-skills-batch66-80-complete,manifest.json,\
		python3 tooling/import_batch66_80_assets.py --check; \
		cd elmos-codex-skills-batch66-80-complete && ./validate.sh)
	python3 tooling/validate_project_synthesis_integration.py $(PROJECT_SYNTHESIS_INTEGRATION_FLAGS)
batch66-80-test-skills:
	$(call guarded,elmos-codex-skills-batch66-80-slightly-strict-tests,manifest.json,\
		python3 tooling/import_batch66_80_strict_test_assets.py --check; \
		cd elmos-codex-skills-batch66-80-slightly-strict-tests && ./validate.sh)
language-packs-batch81-95:
	$(call guarded,elmos-language-packs-batch81-95-complete,package-manifest.json,\
		python3 tooling/import_batch81_95_language_packs.py --check; \
		cd elmos-language-packs-batch81-95-complete && ./validate.sh)
	python3 tooling/validate_project_synthesis_integration.py $(PROJECT_SYNTHESIS_INTEGRATION_FLAGS)
batch81-95-test-skills:
	$(call guarded,elmos-batch81-95-slightly-strict-test-skills,manifest.json,\
		python3 tooling/import_batch81_95_strict_test_assets.py --check; \
		cd elmos-batch81-95-slightly-strict-test-skills && ./validate.sh)
batch97-104-skills:
	$(call guarded,elmos-codex-skills-batch97-104-complete,manifest.json,\
		python3 tooling/import_batch97_104_assets.py --check; \
		cd elmos-codex-skills-batch97-104-complete && ./validate.sh; \
		cd .. && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_batch97_104_skills.py')
	PYTHONDONTWRITEBYTECODE=1 python3 tooling/validate_batch97_104_installed.py
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_batch97_104_installed
.PHONY: spring-golden-route-commercial-skills
spring-golden-route-commercial-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_spring_golden_route_commercial_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s tests/spring-golden-route-commercial -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/spring-golden-route-engine/src python3 -m unittest discover -s engines/spring-golden-route-engine/tests -p 'test_*.py'
product-batch56-skills:
	$(call guarded,elmos-codex-skills-batch56-product-closure,manifest.json,\
		cd elmos-codex-skills-batch56-product-closure && ./validate.sh; \
		cd .. && PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml python tooling/import_product_batch56_closure.py)
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml python -m unittest discover -s tests/product-closure-batch56 -p 'test_*.py'
product-closure-convergence-skills:
	@if test -f elmos-codex-skills-batch56a-product-closure/manifest.json && test -f elmos-product-convergence-reference-skills/manifest.json; then \
		cd elmos-codex-skills-batch56a-product-closure && ./validate.sh && \
		cd ../elmos-product-convergence-reference-skills && PYTHONDONTWRITEBYTECODE=1 python3 scripts/product-convergence/validate_skill_bundle.py . && \
		PYTHONDONTWRITEBYTECODE=1 python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence && \
		PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/product-convergence/test_toolkit.py && \
		cd .. && PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml python tooling/import_product_closure_convergence.py; \
	else \
		PYTHONDONTWRITEBYTECODE=1 python3 tooling/validate_product_closure_convergence_installed.py && \
		PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_product_closure_convergence_installed; \
	fi
	cd batch46-product-convergence-complete-skills && PYTHONDONTWRITEBYTECODE=1 python3 scripts/batch46-complete/validate_skill_bundle.py .
	cd batch46-product-convergence-complete-skills && PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with 'jsonschema>=4.23' python scripts/batch46-complete/validate_convergence_pack.py convergence-packs/reference-product
	cd batch46-product-convergence-complete-skills && PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with 'jsonschema>=4.23' python -m unittest discover -s tests/batch46-complete -p 'test_toolkit.py'
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml python tooling/import_product_convergence_complete.py
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with 'jsonschema>=4.23' python scripts/product-convergence/validate_repository_convergence_bundle.py product-convergence
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml --with jsonschema python -m unittest discover -s tests/product-closure-convergence -p 'test_*.py'
product-closure-gate:
	python3 scripts/product-closure-batch56a/run_product_closure_gate.py templates/product-closure-batch56a/product-closure-gate.example.json --evidence-root .
product-convergence-gate:
	python3 scripts/product-convergence/run_repository_convergence_gate.py product-convergence --evidence-root .
product-batch33-38-skills: product-batch33-39-skills
product-batch33-39-skills: product-batch33-55-skills
product-batch40-55-skills: product-batch33-55-skills
product-batch33-55-skills:
	$(UV) run --quiet --with pyyaml python tooling/validate_product_batch33_55_integration.py
	$(UV) run --quiet --with pyyaml python tooling/ensure_runtime_skill_interfaces.py --check
product-batch35-38: product-batch33-38-skills
	JAVA_HOME="$(JAVA_21_HOME)" "$(MAVEN)" -B -pl modules/source-control-workspace-governance,modules/secure-execution-plane,modules/evidence-assurance-fabric,modules/continuous-authorization,modules/persistence,apps/control-plane -am test
mature-product-toolchain-test:
	$(UV) run --quiet --with 'jsonschema>=4.23' --with pyyaml \
		python -m unittest tests.mature_product_toolkit_extensions_test
	$(UV) run --quiet --with 'jsonschema>=4.23' --with pyyaml \
		python -m unittest tests.batch43_schema_compatibility_test
	$(UV) run --quiet --with 'jsonschema>=4.23' --with pyyaml \
		python -m unittest tests.batch40_supply_chain_test
mature-product-skills: mature-product-toolchain-test b29-skills-test b30-skills-test b31-skills-test batch32-check batch33-check batch34-check batch35-check batch36-check batch37-check batch38-check batch39-check batch40-check batch41-check batch42-check batch43-check batch44-check batch45-check
	$(UV) run --quiet --with jsonschema --with pyyaml python scripts/validate_mature_product_series.py
	$(UV) run --quiet --with 'jsonschema>=4.23' --with pyyaml python -m unittest discover -s tests -p 'mature_product_gate_test.py'
mature-product-packages:
	python3 scripts/package_mature_product_series.py
test-suite-validate:
	$(UV) run --quiet --with pyyaml python scripts/test-suite/validate_skill_bundle.py .
	python3 scripts/test-suite/validate_test_catalog.py test-suites/batch1-37-strict/cases/catalog.json
	python3 scripts/test-suite/validate_coverage_matrix.py test-suites/batch1-37-strict/coverage-matrix.json
	$(UV) run --quiet --with 'jsonschema>=4.23' python scripts/test-suite/validate_schema_bundle.py
	python3 scripts/test-suite/generate_integration_manifest.py --check
	python3 scripts/test-suite/validate_batch1_55_slightly_strict.py
	$(call guarded,elmos-project-synthesis-batch61-65,package-manifest.json,\
		python3 scripts/test-suite/validate_batch1_65_slightly_strict.py)
	$(call guarded,elmos-codex-skills-batch66-80-slightly-strict-tests,manifest.json,\
		python3 tooling/import_batch66_80_strict_test_assets.py --check; \
		cd elmos-codex-skills-batch66-80-slightly-strict-tests && ./validate.sh; \
		cd .. && python3 scripts/test-suite/validate_batch66_80_slightly_strict.py)
	$(call guarded,elmos-batch81-95-slightly-strict-test-skills,package-manifest.json,\
		python3 tooling/import_batch81_95_strict_test_assets.py --check; \
		cd elmos-batch81-95-slightly-strict-test-skills && ./validate.sh; \
		cd .. && python3 scripts/test-suite/validate_batch81_95_language_packs.py)
test-suite-test:
	python3 -m unittest discover -s tests/test-suite -p 'test_*.py'
test-suite-check: test-suite-validate test-suite-test test-suite-b38-45-check test-suite-certification-rehearsal
test-suite-gate:
	python3 scripts/test-suite/run_strict_test_gate.py test-suites/batch1-37-strict
# Covers the trust-anchor validity branches of verify_certification_request --
# revoked, wrong role, wrong algorithm, outside validity window, key digest
# mismatch, missing anchor -- which tests/test-suite/test_toolkit.py does not
# reach. Uses a throwaway key in a temporary directory and grants nothing.
test-suite-certification-rehearsal:
	python3 scripts/test-suite/rehearse_certification_path.py
test-suite-1-55-check:
	python3 scripts/test-suite/validate_batch1_55_slightly_strict.py
	python3 -m unittest tests/test-suite/test_batch1_55_supplemental.py
test-suite-1-55-gate:
	python3 scripts/test-suite/run_batch1_55_slightly_strict_gate.py test-suites/batch1-55-slightly-strict
test-suite-1-65-check:
	$(call guarded,elmos-project-synthesis-batch61-65,package-manifest.json,\
		python3 scripts/test-suite/validate_batch1_65_slightly_strict.py)
	python3 -m unittest tests/test-suite/test_batch1_65_supplemental.py
test-suite-1-65-gate:
	python3 scripts/test-suite/run_batch1_65_slightly_strict_gate.py test-suites/batch1-65-slightly-strict
test-suite-66-80-check: batch66-80-test-skills
	$(call guarded,elmos-codex-skills-batch66-80-slightly-strict-tests,manifest.json,\
		python3 scripts/test-suite/validate_batch66_80_slightly_strict.py)
	python3 -m unittest tests/test-suite/test_batch66_80_supplemental.py
test-suite-66-80-gate:
	python3 scripts/test-suite/run_batch66_80_slightly_strict_gate.py test-suites/batch66-80-slightly-strict
test-suite-81-95-check: batch81-95-test-skills
	$(call guarded,elmos-batch81-95-slightly-strict-test-skills,package-manifest.json,\
		python3 scripts/test-suite/validate_batch81_95_language_packs.py)
	python3 -m unittest tests/test-suite/test_batch81_95_language_packs.py
test-suite-81-95-gate: batch81-95-test-skills
	python3 scripts/test-suite/run_batch81_95_language_pack_gate.py test-suites/batch81-95-language-packs-slightly-strict
test-suite-b38-45-validate:
	python3 scripts/test-suite-b38-45/validate_skill_bundle.py .
	python3 scripts/test-suite-b38-45/validate_test_catalog.py test-suites/batch38-45-strict/cases/catalog.json
	python3 scripts/test-suite-b38-45/validate_coverage_matrix.py test-suites/batch38-45-strict/coverage-matrix.json
	$(UV) run --quiet --with 'jsonschema>=4.23' python scripts/test-suite-b38-45/validate_schema_bundle.py
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
	PATH="$(DOTNET_PATH_PREFIX):$$PATH" $(DOTNET) test engines/dotnet-engine/Elmos.Dotnet.slnx
python:
	$(UV) --directory engines/python-engine run --locked pytest
	$(UV) --directory engines/python-engine run --locked ruff check src tests
	$(UV) --directory engines/python-engine run --locked mypy src
project-synthesis:
	python3 tooling/validate_project_synthesis_integration.py $(PROJECT_SYNTHESIS_INTEGRATION_FLAGS)
	$(UV) --directory engines/project-synthesis-engine run --locked python ../../scripts/operations/validate_generation_support_matrix.py
	$(call guarded,elmos-project-synthesis-batch61-65,package-manifest.json,\
		$(UV) run --quiet --with 'jsonschema>=4.23' python tooling/validate_project_synthesis_batch61_65_schemas.py)
	$(UV) --directory engines/project-synthesis-engine run --locked pytest
	$(UV) --directory engines/project-synthesis-engine run --locked ruff check src tests scripts
	$(UV) --directory engines/project-synthesis-engine run --locked mypy src
	$(UV) --directory engines/project-synthesis-engine run --locked python scripts/run_acceptance.py
	$(UV) --directory engines/project-synthesis-engine run --locked python scripts/run_production_matrix.py
toolchains-validate:
	python3 scripts/toolchains/runtime_environment.py validate
toolchains-doctor: toolchains-validate
	python3 scripts/toolchains/runtime_environment.py doctor --profile "$(PROFILE)" --output "$(RUNTIME_STATUS_OUTPUT)"
toolchains-check: toolchains-validate
	python3 scripts/toolchains/runtime_environment.py doctor --profile core --strict
	python3 scripts/toolchains/runtime_environment.py doctor --profile synthesis --strict
	@if [ "$$(uname -s)/$$(uname -m)" = "Darwin/arm64" ]; then \
		python3 scripts/toolchains/runtime_environment.py doctor --profile routes-macos --strict; \
	else \
		printf '%s\n' 'routes-macos status=NOT_APPLICABLE'; \
	fi
toolchains-install: toolchains-validate
	python3 scripts/toolchains/runtime_environment.py install --profile "$(PROFILE)"
toolchains-env: toolchains-validate
	python3 scripts/toolchains/runtime_environment.py env --profile "$(PROFILE)"
project-synthesis-toolchains:
	python3 scripts/toolchains/runtime_environment.py install --profile synthesis
	$(UV) --directory engines/project-synthesis-engine run --locked python scripts/run_acceptance.py --require-all-toolchains
frontend:
	CI=true PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir engines/frontend-client-engine install --frozen-lockfile
	PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir engines/frontend-client-engine check
sql-transpiler:
	$(UV) --directory engines/database-data-engine/sql-transpiler run --locked pytest
	$(UV) --directory engines/database-data-engine/sql-transpiler run --locked ruff check src tests
	$(UV) --directory engines/database-data-engine/sql-transpiler run --locked mypy src
sql-dialect:
	$(UV) --directory engines/sql-dialect-engine run --locked --extra dev pytest
	$(UV) --directory engines/sql-dialect-engine run --locked --extra dev ruff check src tests
	$(UV) --directory engines/sql-dialect-engine run --locked --extra dev mypy --ignore-missing-imports src

# What the polyglot engine actually does right now, by running it rather than
# by reading it. Every capability question here had been answered by reading
# code, and reading code has a specific failure mode: a rejection code in an
# intermediate layer is not the system's boundary. `discover_unit()` refuses a
# multi-function file; `discover_repository()` then splits that same result
# into one READY unit per function. Only the second is the boundary.
#
# Rows reading NOT_PROBED mean this machine lacks that language's pinned
# toolchain. That is an instruction to re-run somewhere that has it, never a
# capability claim -- which is why this is a report, not a gate.
.PHONY: capability-probe capability-probe-json capability-probe-tests
capability-probe:
	$(UV) --directory engines/polyglot-route-engine run --locked python tools/capability_probe.py

capability-probe-json:
	$(UV) --directory engines/polyglot-route-engine run --locked python tools/capability_probe.py --json

# The assertions over a real probe run. Kept off the default suite on purpose:
# they drive every language's real toolchain, take minutes, depend on what this
# machine has installed, and once wedged a full pytest run at 0% CPU for over
# ten minutes. A suite that can hang forever cannot gate anything.
capability-probe-tests:
	ELMOS_CAPABILITY_PROBE_TESTS=1 $(UV) --directory engines/polyglot-route-engine run --locked \
		python -m pytest -q tests/test_capability_probe.py
# The component engine drives real framework toolchains (TypeScript,
# @vue/compiler-sfc, vue-template-compiler, @angular/compiler,
# svelte/compiler, @wxml/parser) plus real SSR renderers, so its tests are
# serialised: parallel Jest workers each spawn compiler subprocesses and
# contend for I/O.
component-dialect:
	cd engines/component-dialect-engine && CI=true PATH="$(NODE_RUNTIME_BIN):$$PATH" npm ci --no-audit --no-fund
	cd engines/component-dialect-engine && PATH="$(NODE_RUNTIME_BIN):$$PATH" npm run build
	cd engines/component-dialect-engine && PATH="$(NODE_RUNTIME_BIN):$$PATH" npx jest --runInBand
web:
	CI=true PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir apps/web-console install --frozen-lockfile
	PATH="$(NODE_RUNTIME_BIN):$$PATH" $(PNPM) --dir apps/web-console check
up:
	docker compose -f deploy/compose/docker-compose.yml up --build
down:
	docker compose -f deploy/compose/docker-compose.yml down
local-commercial-up:
	python3 scripts/operations/local_commercial.py up
local-commercial-smoke:
	python3 scripts/operations/local_commercial.py smoke
local-commercial-status:
	python3 scripts/operations/local_commercial.py status
local-commercial-down:
	python3 scripts/operations/local_commercial.py down

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
include Makefile.batch46


# --- java->python UIR route -------------------------------------------------
# TREE, WORKSPACE and SOURCE are overridable:
#   make uir-j2p-survey TREE=engines/enterprise-suite-engine/src
UIR_J2P_DIR := engines/uir-java-python
TREE ?= .
WORKSPACE ?= /tmp/uir-j2p-workspace
SOURCE ?= $(CURDIR)/engines/uir-java-python

uir-j2p-deps:
	python3 -m pip install -r $(UIR_J2P_DIR)/requirements.txt

uir-j2p-test:
	cd $(UIR_J2P_DIR) && python3 -m unittest discover -s tests -v

uir-j2p-mutation:
	cd $(UIR_J2P_DIR) && python3 tools/mutation_check.py --json-out docs/mutation-report.json

uir-j2p-survey:
	cd $(UIR_J2P_DIR) && python3 -m j2p.cli survey $(CURDIR)/$(TREE) --out docs/survey-latest.json

# The control measurement: the same survey with whole-program resolution turned
# off. A claim that cross-file resolution moved the number is only worth
# something if the unimproved number can still be reproduced on demand.
uir-j2p-survey-noindex:
	cd $(UIR_J2P_DIR) && python3 -m j2p.cli survey $(CURDIR)/$(TREE) --no-index --out docs/survey-noindex.json

uir-j2p-evidence:
	cd $(UIR_J2P_DIR) && python3 tools/record_batch_evidence.py \
	  --runtime $(CURDIR)/skills/repository-migration-platform-skills-batch1-38/scripts/migration_platform.py \
	  --workspace $(WORKSPACE) --source $(SOURCE) --survey-tree $(CURDIR)/$(TREE)

# The gate is test + mutation together: a green suite that no mutation can turn
# red is not evidence of anything.
uir-j2p-gate: uir-j2p-test uir-j2p-mutation

.PHONY: uir-j2p-deps uir-j2p-test uir-j2p-mutation uir-j2p-survey uir-j2p-survey-noindex uir-j2p-evidence uir-j2p-gate

.PHONY: multitenant-task-finops-skills
multitenant-task-finops-skills:
	PYTHONDONTWRITEBYTECODE=1 python3 tooling/integrate_multitenant_task_finops_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python -m unittest discover -s tests/multitenant-task-finops -p 'test_*.py'

.PHONY: spring-golden-route-commercial-task-inventory
spring-golden-route-commercial-task-inventory:
	PYTHONDONTWRITEBYTECODE=1 python3 tooling/validate_spring_golden_route_source_task_coverage.py --check
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/spring-golden-route-commercial/test_source_task_coverage.py

.PHONY: etgb-sota-skills
etgb-sota-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 tooling/integrate_etgb_sota_skills.py
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m unittest discover -s engines/etgb-engine/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) validate --archive skills/subskills/elmos-etgb-sota-skills-package-v1.1.0.tar.gz --extracted skills/subskills/elmos-etgb-sota-skills-package-v1.1.0
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) coverage
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) materialize --output .elmos/etgb/materialized.json
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) run --profile smoke --output .elmos/etgb/smoke-results-v11.jsonl --artifact-root .elmos/etgb/evidence-v11
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) score .elmos/etgb/smoke-results-v11.jsonl --expected-count 4 --output .elmos/etgb/smoke-score-v11.json
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) gate .elmos/etgb/smoke-results-v11.jsonl --profile smoke --output .elmos/etgb/smoke-gate-v11.json

.PHONY: etgb-full-product-skills etgb-skills
etgb-skills: etgb-full-product-skills

etgb-full-product-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 tooling/integrate_etgb_full_product_skills.py
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m unittest discover -s engines/etgb-engine/tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) validate --archive skills/subskills/elmos-etgb-full-product-assurance-skills-package-v2.0.0.zip --extracted skills/elmos-etgb-full-product-assurance-skills-package-v2.0.0
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) coverage
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) feature-coverage
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) materialize --output .elmos/etgb/materialized-v20.json
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) run --profile smoke --output .elmos/etgb/smoke-results-v20.jsonl --artifact-root .elmos/etgb/evidence-v20
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) score .elmos/etgb/smoke-results-v20.jsonl --expected-count 4 --output .elmos/etgb/smoke-score-v20.json
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 --with 'cryptography>=42.0,<47.0' env PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb --repo-root $(CURDIR) gate .elmos/etgb/smoke-results-v20.jsonl --profile smoke --output .elmos/etgb/smoke-gate-v20.json

.PHONY: functional-assurance-skills
functional-assurance-skills:
	PYTHONDONTWRITEBYTECODE=1 $(UV) run --no-project --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python3 tooling/integrate_functional_assurance_certification_skills.py --check
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=engines/functional-assurance-engine/src $(UV) run --no-project --quiet --with pytest --with pyyaml==6.0.2 --with jsonschema==4.25.1 python3 -m pytest engines/functional-assurance-engine/tests -v


