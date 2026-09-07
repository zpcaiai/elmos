---
name: approval-gate-planner
description: Generate blocking human and evidence approval gates for ELMOS migration plans. Use for Security, database, transaction, API, high-risk or inconclusive compatibility decisions.
---
# Approval Gate Planner

## Workflow
1. Create gates before every sensitive or policy-exceeding step.
2. Specify gate owner type, reason and required evidence.
3. Add evidence gates for unknown build, JDK, vulnerability or compatibility data.
4. Persist decisions with actor and time; never overwrite historical decisions.

## Acceptance
- Pending blocking gates prevent execution.
- Agents and project code cannot approve their own gates.
- Rejected or expired evidence requires a new decision.

