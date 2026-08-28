# OpenHands Absorption P0/P1 Implementation

The supplied archive is an untrusted specification package, not executable
authority. Repository code independently pins SHA-256
`72d151a4d76d3ec4e1e7b7d7401e4c1e390a9ed1a49da19ce4061e45725c3c99`,
validates its 50-member safe-path inventory and exact 14 Skill identities, and
never executes its installer, verifier, SQL, workflow or prompts.

All P0-01 through P0-09 and P1-01 through P1-05 capabilities now have concrete
repository-owned modules, persistence contracts, migration/rollback assets,
negative tests and fail-closed evidence state. The canonical machine-readable
mapping is
`engines/openhands-absorption-engine/src/elmos_openhands/implementation_manifest.json`;
`tools/validate_engine.py` rejects missing modules/tests, source drift or any
premature external-success/certification status.

| Capability | Main code implementation |
|---|---|
| P0-01 Stateless runtime | `runtime.py`, `supervisor.py`, `service.py`, `api.py` |
| P0-02 Immutable ledger | `ledger.py`, `postgres.py`, `persistence.py`, `projections.py` |
| P0-03 Action/Observation | `protocol.py`, `tools.py`, `workspace_api.py` |
| P0-04 Persistence/replay | `replay.py`, `postgres.py`, `persistence.py`, `governance.py` |
| P0-05 Workspace/sandbox | `workspace.py`, `sandbox.py`, `workspace_api.py` |
| P0-06 Runtime plane | `plane.py`, `orchestration.py`, `api.py`, `observability.py` |
| P0-07 Context/condenser | `context.py`, `projections.py` |
| P0-08 Firewall/security | `firewall.py`, `policy.py` |
| P0-09 Hooks/gates | `gates.py`, `evidence.py`, `qualification.py` |
| P1-01 Skill disclosure | `skills.py`, `skill_routing.py` |
| P1-02 Capability package | `packages.py`, `governance.py` |
| P1-03 Agent DAG | `dag.py`, `orchestration.py`, `supervisor.py` |
| P1-04 Provider adapters | `providers.py`, `provider_sessions.py` |
| P1-05 Browser evidence | `browser.py`, `browser_drivers.py`, `evidence.py` |

The implementation distinguishes four states:

1. `IMPLEMENTED`: repository code and contracts exist for all 14 Skills.
2. `LOCAL_ENGINEERING_EVIDENCE`: deterministic local gates have actually run.
3. `NOT_RUN`: named external or production-equivalent campaigns have not run.
4. `NOT_CERTIFIED` / `NOT_GA`: no production certification or GA decision exists.

Only signed, digest-bound evidence from the named environment and an independent
verifier can advance an external campaign to `READY_FOR_EXTERNAL_GATE`. Runtime
code deliberately has no path that emits `CERTIFIED` or `GA`.

Further operational artifacts:

- [补全计划](COMPLETION_PLAN.md)
- [测试计划](TEST_PLAN.md)
- [实现追踪矩阵](IMPLEMENTATION_MATRIX.md)
- [生产接入、故障与回滚 Runbook](RUNBOOK.md)
- [威胁模型](THREAT_MODEL.md)

代码实现已完成；本地 disposable 探针已产生局部工程 evidence，但真实生产等价
Temporal/PostgreSQL、生产 sandbox、外部 Provider 成功、physical device、独立
holdout、代表性 load/Chaos 和独立安全审查尚未闭合，因此总体保持
`NOT_CERTIFIED / NOT_GA`，不能冒充生产认证或 GA。执行明细见
`evidence/QUALIFICATION_EXECUTION_2026-08-28.md`。
