# ELMOS Codex Skills — Batch 34–38 Complete

## Package inventory

This package contains **188 installable Codex Skills**:

- **Batch 34 — 18 Skills:** Enterprise Identity、Multi-tenancy与Access Governance
- **Batch 35 — 33 Skills:** SCM Provider与Advanced Repository Workspace
- **Batch 36 — 41 Skills:** Private Runner Fleet、Sandbox与Execution Operations
- **Batch 37 — 48 Skills:** Artifact、Evidence Producer与Assurance Analytics
- **Batch 38 — 48 Skills:** Policy Automation、Policy Intelligence与Regulatory Operations

## Sub-batch counts

- `34A`: 6 — Tenant Foundation与Isolation
- `34B`: 6 — Human Identity与Access Governance
- `34C`: 6 — Workload Identity与Credential Governance
- `35A`: 11 — GitHub Cloud／GHES SCM Connector
- `35B`: 11 — Unified Multi-provider SCM
- `35C`: 11 — Advanced Repository Workspace
- `36A`: 11 — Private Runner Fleet
- `36B`: 15 — Task Sandbox Execution Plane
- `36C`: 15 — Runner Execution Operations
- `38A`: 16 — Policy、Control Automation与Continuous Authorization
- `38B`: 16 — Policy Intelligence与Governance Engineering
- `38C`: 16 — Governance Workflow与Regulatory Operations
- `37A`: 16 — Artifact、Provenance 与 Evidence Fabric
- `37B`: 16 — Evidence Producer Integrations
- `37C`: 16 — Evidence Analytics 与 Assurance Cockpit

## Layout

```text
agent-skills/runtime/<skill-name>/SKILL.md
docs/batch-<subbatch>-overview.md
references/
templates/
scripts/
AGENTS.md
manifest.json
install.sh
validate.sh
```

## Install

```bash
./install.sh ~/.codex/skills
```

## Validate

```bash
./validate.sh
```

## Provenance note

- Batch 37's 48 Skills are copied from the previously validated Batch 37 Complete package.
- Batch 34, 35, 36 and 38 are normalized as installable Skills from the approved A/B/C architecture and named Skill definitions produced in the conversation.
- Structural validation does not mean a real ELMOS repository, provider, database migration or production certification gate has already passed.
