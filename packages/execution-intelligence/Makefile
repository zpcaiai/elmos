PY ?= python3
CLI := PYTHONPATH=src $(PY) -m elmos_execution_intelligence.cli
REPO_ROOT ?= ../..
OUT ?= estimation/elmos
STORE ?= estimation/elmos/run.db
PROJECT ?= profiles/elmos/project-profile.json
TASKS ?= profiles/elmos/task-dag.json
# The bundled registry records time-bounded public list-price provenance. Re-verify
# it or override it with an authorized account rate card before budgeting.
PRICING ?= config/model-pricing.json
PG_DSN ?= postgresql://postgres@localhost:5432/elmos_ei
TASK_ID ?= matrix-medium
UNITS ?= 156
GIT_LOG ?= /tmp/git.log
GIT_SCOPE ?= engines/polyglot-route-engine
TRUST_STORE ?=
TRUST_STORE_SHA256 ?=
CERTIFY_TRUST_ARGS = $(if $(TRUST_STORE),--trust-store "$(TRUST_STORE)",) \
	$(if $(TRUST_STORE_SHA256),--trust-store-sha256 "$(TRUST_STORE_SHA256)",)

.PHONY: lint test scan audit dag validate forecast plan execute route chaos calibrate certify schemas pg-conformance ingest advise anchor mix durations serve all clean-outputs

# ruff E,F,I,B,UP,S at 120 columns and mypy --strict: the same gate the route
# engine runs under. Record the result for each exact commit; this file makes no
# claim about the current worktree having passed.
lint:
	$(PY) -m ruff check --no-cache src tests
	MYPYPATH=$$PWD/src $(PY) -m mypy --strict -p elmos_execution_intelligence

test:
	$(PY) -m pytest -q tests

scan:
	$(CLI) scan-tokens $(REPO_ROOT) --ignore-dir _to_delete --ignore-dir .ai-tmp \
		--ignore-dir artifacts --output estimation/elmos-token-scan.json

audit:
	$(CLI) audit-scope $(REPO_ROOT) --static-scan estimation/elmos-token-scan.json \
		--project-id elmos --output $(OUT)

dag:
	$(CLI) decompose --scope $(OUT)/scope-baseline.json --dag-id elmos-generated --output $(OUT)

validate:
	$(CLI) validate --project $(PROJECT) --tasks $(TASKS) --pricing $(PRICING)

forecast: validate
	$(CLI) forecast --project $(PROJECT) --tasks $(TASKS) --pricing $(PRICING) \
		--static-scan estimation/elmos-token-scan.json --output $(OUT)

plan:
	$(CLI) plan --project $(PROJECT) --tasks $(TASKS) --output $(OUT)

execute:
	$(CLI) execute --project $(PROJECT) --tasks $(TASKS) --store $(STORE) --output $(OUT)

route:
	$(CLI) route --tasks $(TASKS) --pricing $(PRICING) --output $(OUT)

chaos:
	$(CLI) chaos --project $(PROJECT) --output $(OUT)

calibrate:
	$(CLI) calibrate --history $(OUT)/telemetry.jsonl --output $(OUT)
	$(CLI) apply-calibration --tasks $(TASKS) --profiles $(OUT)/estimator-profiles.json \
		--output $(OUT)/task-dag.calibrated.json

certify:
	$(CLI) certify --evidence $(OUT) $(CERTIFY_TRUST_ARGS)

schemas:
	$(CLI) validate-schemas $(OUT)

# Runs the store conformance suite against a real PostgreSQL as well as SQLite.
# Without ELMOS_EI_PG_DSN the PostgreSQL cases are skipped -- and reported as
# skipped, never as passes.
pg-conformance:
	ELMOS_EI_PG_DSN=$(PG_DSN) $(PY) -m pytest -q tests/test_store_conformance.py

# Turns real run artefacts into calibrate rows. Pick one source:
#   LOG=...        a pytest summary line       -> aggregate mean per node
#   DURATIONS=...  a --durations=0 log         -> a real duration per node
#   TRANSCRIPT=... an agent session JSONL      -> real TOKEN counts
ingest:
	$(CLI) ingest-telemetry --tasks $(TASKS) --task-id $(TASK_ID) \
		$(if $(TRANSCRIPT),--transcript $(TRANSCRIPT),) \
		$(if $(DURATIONS),--durations-log $(DURATIONS) --unit-count $(UNITS),) \
		$(if $(LOG),--pytest-log $(LOG) --unit-count $(UNITS),) \
		--output $(OUT)-real

# Which sections of an oversized SKILL.md to move to references/.
advise:
	$(CLI) advise-skills --static-scan estimation/elmos-token-scan.json --output $(OUT)

# Produce a COMPLETE per-node durations log for this package's own suite.
#
# --durations=0 alone is not enough: pytest hides entries below 0.005s, and the
# hidden ones are the fast ones. On this suite that silently drops 69% of nodes
# and inflates the mean 2.9x. --durations-min=0 is what makes it complete, and
# the ingester refuses a truncated log rather than calibrating on a skewed one.
DURATIONS_LOG ?= /tmp/elmos-ei-durations.log
durations:
	$(PY) -m pytest tests -q --durations=0 --durations-min=0 | tee $(DURATIONS_LOG)
	@echo "wrote $(DURATIONS_LOG) — ingest with:"
	@echo "  $(CLI) ingest-telemetry --durations-log $(DURATIONS_LOG) --task <id> --unit-count <n> ..."

# Compare the forecast's assumed token category mix against real observed usage.
# TRANSCRIPT must point at an agent session record (Claude Code / Codex JSONL) --
# it is the only artifact that carries real token counts. Repeat --transcript for
# more sessions; one session is a finding, not a calibration.
TRANSCRIPT ?=
mix:
	@test -n "$(strip $(TRANSCRIPT))" || { \
		echo "BLOCKED: set TRANSCRIPT to one or more explicitly authorized session JSONL paths" >&2; \
		exit 3; \
	}
	$(CLI) token-mix --tasks $(OUT)/task-dag.json \
		--forecast $(OUT)/token-forecast.json \
		--pricing config/model-pricing.json \
		$(foreach t,$(wildcard $(TRANSCRIPT)),--transcript $(t)) \
		--output $(OUT)

# A human-effort anchor from the repository's own history. Produce the export first:
#   git -c gc.auto=0 log --no-merges --date=short \
#       --pretty=format:'%H%x09%an%x09%ad%x09%s' -- engines/ > /tmp/git.log
anchor:
	$(CLI) human-anchor --git-log $(GIT_LOG) --scope $(GIT_SCOPE) \
		--forecast $(OUT)/project-forecast.json --output $(OUT)

# The reference HTTP server for the task-execution API contract.
serve:
	$(CLI) serve --store $(STORE) --port 8787

all: lint test scan audit dag forecast plan execute route chaos calibrate advise mix schemas certify
