---
name: version-platform-and-support-planner
description: Resolve exact target versions and verify runtime, OS, architecture, deployment, support, and maintenance compatibility. Use before target dependency approval.
---
# Version Platform And Support Planner
Read `../references/dependency-migration-v1.md`. Evaluate exact versions against target runtime/framework/build-tool constraints, OS/architecture/libc/native assets, deployment modes, offline policy, release/support windows and transitive constraints. Produce a platform matrix, upgrade/downgrade rationale, pinning policy and unresolved conflicts. Do not use floating/latest versions, assume source-platform support transfers, or label an abandoned/unverified package supported. Any required cell without evidence blocks automatic selection.
