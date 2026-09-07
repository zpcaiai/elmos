---
name: dotnet-engine-contract-and-worker
description: Operate the independent ELMOS .NET 10 engine through the shared versioned Engine API while preserving tenant, Runner, evidence, cancellation, and idempotency boundaries.
---

# .NET Engine Contract and Worker

Use this skill for .NET scan, plan, execution, validation, capability, job-status, or cancellation work.

## Boundary

- Use `GET /engine/v1/capabilities` and the shared scan, plan, execute-step, validate, job, and cancel paths.
- Require server-derived `organizationId`, immutable snapshot reference, approved workspace reference, correlation ID, and idempotency key.
- Scope idempotency to organization, operation, engine version, snapshot/profile/toolchain inputs.
- Route `WINDOWS_LEGACY`, `MODERN_WINDOWS`, and `MODERN_LINUX` separately.
- Never access the control-plane database, GitHub implementation, billing internals, or control-plane secrets.
- Never create orders, approve risk or PRs, merge code, or change organization policy.

## Workflow

1. Read capabilities and reject an incompatible engine/toolchain version.
2. Verify that the workspace is inside the leased Runner root and corresponds to the immutable snapshot.
3. Select the Runner profile from the approved migration step; do not infer Linux readiness from a Windows build.
4. Submit the command once with a stable idempotency key and persist only returned evidence references in the control plane.
5. Poll the tenant-scoped job, support cancellation, and retain the historical result under its original engine version.
6. Map errors to the shared error envelope. Preserve `NOT_RUN`, `BLOCKED`, and partial states.

## Route specialized work

Use the other Batch 11 Runtime Skills for the substance of each phase: `solution-msbuild-project-discovery`, `dotnet-framework-technology-fingerprint`, `roslyn-semantic-symbol-and-call-graph`, `dotnet-target-profile-and-migration-planner`, `sdk-project-and-nuget-modernizer`, `dotnet-modernization-tool-adapters`, `aspnet-framework-to-aspnet-core-migrator`, `wcf-to-corewcf-grpc-rest-migrator`, `ef6-to-efcore-modernizer`, `dotnet-build-contract-and-behavior-validator`, and `dotnet-elmos-unified-evidence-integration`. Keep this skill as the Engine/API and Worker authority boundary.

## Required output

Return a versioned job response containing job status, evidence references, structured result, and a sanitized error where applicable. Capability output must identify `ELMOS_DOTNET`, C# full support, VB inventory, SLN/SLNX/SLNF, project formats, frameworks, migration capabilities, and Runner profiles.

## Fail closed

Reject ambiguous solutions, missing MSBuild/targeting packs, unsupported project types, unavailable Windows or modern .NET Runners, workspace escape, cross-tenant job access, or requests to execute external agents in-process.
