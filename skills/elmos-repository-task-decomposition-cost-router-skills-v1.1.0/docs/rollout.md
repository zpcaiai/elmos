# Production rollout plan

## Phase 0 — shadow planning
Run decomposition/routing but let the existing process implement. Compare proposed routes with actual outcomes.

## Phase 1 — low-risk leaf tasks
Enable L0/L1 workers for tests, docs, adapters, DTOs, simple UI and bounded service changes. Require deterministic validation.

## Phase 2 — parallel DAG waves
Enable path-locked worktrees, integration manager and retry/escalation controller.

## Phase 3 — high-risk gates
Enable security, migration and concurrency promotion/review policies.

## Phase 4 — adaptive routing
Enable telemetry-driven success probabilities, expected total cost routing and policy backtests.

## Phase 5 — repository certification
Block task completion until end-to-end acceptance and traceability are satisfied.

Suggested KPIs: first-pass task success, completed-task cost, total run cost, escaped-defect rate, integration-conflict rate, autonomous P50/P90 wall-clock, percentage of tasks handled by L0/L1, escalation rate, cache hit ratio and final acceptance pass rate.
