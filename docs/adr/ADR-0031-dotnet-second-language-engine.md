# ADR-0031: .NET is a second execution engine, not a second control plane

## Status

Accepted for Batch 11 on 2026-07-21.

## Context

ELMOS already owns immutable snapshots, organizations and authorization, durable workflow and approvals, Runner leases, secrets, evidence, usage/billing, audit, SCM, delivery and rollback. Reimplementing these in C# would create inconsistent authority and cross-tenant failure modes. At the same time, .NET Framework modernization needs Windows/Visual Studio tooling, MSBuild evaluation and Roslyn semantics that must not be loaded into the Java control plane.

Microsoft's Roslyn Workspace model provides Solution, Project, Document, syntax, semantic and Compilation views, so C# semantic claims use Roslyn instead of source regex. The .NET 10 toolchain supports SLN/SLNX/SLNF handling. Upgrade Assistant is now deprecated in favor of GitHub Copilot modernization, so it is retained only as a non-authoritative legacy adapter; Roslyn remains the deterministic core.

## Decision

Implement `engines/dotnet-engine` as an independently deployable .NET 10 Worker behind the same `/engine/v1` capability, scan, plan, execute-step, validate, job and cancel contract. Java routes by language through `ModernizationEnginePort`; it does not link Roslyn or MSBuild. Engine jobs and status access are tenant scoped and idempotent.

Static project discovery disables DTD/external XML resolution and never evaluates MSBuild. Dynamic `MSBuildWorkspace` loading is permitted only inside a leased network-denied Windows sandbox without control-plane secrets. Windows Legacy, Modern Windows and Modern Linux are different Runner capabilities and evidence environments.

The engine emits versioned .NET evidence extensions while reusing shared findings, plans, workflow, risk, usage, audit, portfolio, SCM, evidence-pack and delivery objects. Independent validation—not the transformer or an agent—decides promotion.

## Consequences

- ASP.NET Web Forms UI is a rewrite/side-by-side decision, not an automatic conversion claim.
- CoreWCF is a candidate selected by binding/client/behavior evidence, not a universal WCF answer.
- EF6 may remain during the first modern-runtime stage; EF Core migration is per context, and EDMX/migration history are re-baselined rather than copied.
- A Windows build cannot prove Linux portability, and disappeared tests fail validation.
- Image definitions remain unselectable until digest, SBOM, vulnerability, provenance, secret-scan and smoke-test evidence are approved.

## References

- [Roslyn Workspace model](https://learn.microsoft.com/en-us/dotnet/csharp/roslyn-sdk/work-with-workspace)
- [.NET Upgrade Assistant deprecation](https://learn.microsoft.com/en-us/dotnet/core/porting/upgrade-assistant-install)
- [.NET support policy](https://dotnet.microsoft.com/en-us/platform/support/policy)
- [EF6 and EF Core side by side](https://learn.microsoft.com/en-us/ef/efcore-and-ef6/side-by-side)
