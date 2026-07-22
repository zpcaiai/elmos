---
name: dotnet-target-profile-and-migration-planner
description: Select conservative, modern Windows, cross-platform, side-by-side, or redesign targets and emit a Solution-level migration DAG.
---

# .NET Target Profile and Migration Planner

Use discovery, fingerprint, Roslyn/API, baseline, deployment, support, downtime, package/provider and test-readiness evidence. Do not let a modernization tool or coding agent select the target.

## Candidates

Always compare at least a minimum safe .NET Framework path, `.NET 10` modern Windows path, and `.NET 10` cross-platform path. Add incremental side-by-side for large ASP.NET/System.Web, Web Forms, staged WCF, or per-context EF migration. Use strategic redesign when the application model has no safe direct equivalent.

Registry, services, COM, Office interop and equivalent Windows dependencies prevent a Linux recommendation until removed or replaced. Web Forms UI is `REWRITE_REQUIRED`; it is not automatically translated. Custom WCF bindings and EDMX require explicit architecture/data decisions.

## DAG

Order leaf/shared libraries before hosts; baseline before project-system changes; SDK/PackageReference before runtime/framework moves; ASP.NET/WCF/EF transitions before deterministic Roslyn repair; and independent Windows/Linux/contract/data/performance validation after changes. Record dependencies, Runner profile, executor, approval and validation gates per step.

## Required output

Produce candidate target profiles, scored recommendation with assumptions, migration DAG, waves, risks, blockers, and approval gates. Conservative, balanced, and strategic policies must remain distinguishable. Unknown evidence increases risk or blocks; it never silently lowers risk.
