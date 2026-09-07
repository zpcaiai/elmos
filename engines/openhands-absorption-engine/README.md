# ELMOS OpenHands Absorption Engine

Repository-owned code implementation of all 14 capabilities in the supplied
`elmos-openhands-absorption-p0-p1-v1.0.0` specification package. The ZIP is
digest-pinned, inspected as untrusted data, and never imported or executed.

The implementation includes:

- stateless turns, durable supervision, cancellation, budgets and fail-closed
  completion;
- SQLite engineering persistence and real PostgreSQL/RLS/outbox/CAS adapter
  code with forward and rollback migrations;
- typed Action/Observation protocols, workspace APIs, reconciliation and a
  governed Tool Gateway;
- local, Docker, Kubernetes, Firecracker and attested enterprise-SSH sandbox
  backends with explicit isolation classes and secret leases;
- durable worker/admission/event-stream APIs, REST/WebSocket/gRPC gateways and
  Temporal workflow definitions with dynamic DAG updates, compensation and
  continue-as-new state transfer;
- evidence-aware context projections, immutable signed evidence packs,
  retention/export/deletion governance and OTel/FinOps adapters;
- policy DSL, taint tracking, scoped approvals, kill switches and completion
  gates;
- progressive Skill routing/disclosure, deterministic signed capability
  bundles, registry lifecycle, pin/revoke/rollback and conformance contracts;
- durable Codex, Claude, OpenHands, OpenCode, Gemini and Junie provider session
  adapters with normalized streams, checkpoints, cancellation, usage and
  policy/cost/privacy routing;
- Playwright browser/device drivers, semantic locators, privacy masking,
  binary-safe evidence capture, allowlist governance and flake blocking;
- executable qualification control for real PostgreSQL/Temporal, sandbox,
  Provider, browser/device, Golden Repo, load, Chaos and independent-security
  campaigns.

The exact Skill-to-module-to-test bindings and fail-closed external status are
machine-readable in
`src/elmos_openhands/implementation_manifest.json` and enforced by
`tools/validate_engine.py`.

## Install

The deterministic local engine uses Python's standard library plus the core
`cryptography` dependency required for Ed25519 evidence verification. Production
integrations remain explicit optional dependencies:

```bash
python -m pip install -e 'engines/openhands-absorption-engine[production]'
playwright install --with-deps
```

Installing dependencies does not execute or qualify any external environment.

## Validate

From the repository root:

```bash
make openhands-absorption
PYTHONPATH=engines/openhands-absorption-engine/src uv run \
  --project engines/openhands-absorption-engine --locked python -m elmos_openhands status
```

To materialize—but not execute—a digest-bound qualification plan:

```bash
PYTHONPATH=engines/openhands-absorption-engine/src python -m elmos_openhands \
  qualification-plan \
  --target-digest sha256:<64-lowercase-hex> \
  --environment-digest sha256:<64-lowercase-hex>
```

## Evidence boundary

代码实现已完成；本地 disposable PostgreSQL/Temporal、L1 sandbox、browser
matrix、Golden Repo、bounded load/Chaos 和 Bandit 已有工程 evidence，但生产等价
拓扑、生产 sandbox、外部 Provider 成功、physical device、独立 holdout、代表性
soak、独立安全审查和客户验收仍为 `NOT_RUN`。Provider 当前真实探针为 `FAIL`
（quota/endpoint），总体保持 `NOT_CERTIFIED / NOT_GA`，不能冒充生产认证或 GA。
详见 `docs/openhands-absorption/evidence/QUALIFICATION_EXECUTION_2026-08-28.md`。

Local unit, contract, lint, type and static integration results are engineering
evidence only. The code never promotes those results to external qualification,
production certification or GA.
