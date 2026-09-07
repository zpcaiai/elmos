# Changelog

## 1.1.0
- Added `elmos-model-selection-controller` (Skill 36).
- Added page/API support for Smart per-task routing or user-selected model execution across the fixed ten-model allowlist.
- Added manual strict vs allowlisted smart fallback behavior and verification-policy handling.
- Added model selection schema/config/UI contract, audit events and planned-vs-actual model usage fields.
- Updated orchestrator, router, registry guard, executor, retry controller, examples and runtime instructions.

## 1.0.0
- Initial 36-skill package.
- Hard 10-model allowlist.
- Cost/performance routing with risk floors and retry escalation.
- Repository-level DAG execution, worktree isolation, integration and certification.
- Durable state/resume, autonomous ETA and telemetry learning.
