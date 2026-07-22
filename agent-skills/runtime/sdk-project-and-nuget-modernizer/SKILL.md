---
name: sdk-project-and-nuget-modernizer
description: Deterministically convert legacy C# projects and packages.config to SDK-style and PackageReference while preserving behavior and enabling staged net48-first migration.
---

# SDK Project and NuGet Modernizer

Use this skill only after a passing Windows baseline and complete static project/import inventory.

## Workflow

1. Pin the approved SDK in `global.json` and record NuGet sources/locks without credentials.
2. Convert `packages.config` entries to explicit `PackageReference`; compare package ID/version/assets graphs before and after.
3. Convert legacy csproj to SDK style while initially retaining `net48`/the approved Framework where staging is safer.
4. Preserve non-default compile/content behavior, linked files, resources, signing, assembly metadata, COM/native references, custom targets/imports/tasks, transforms, generators and conditions. Anything not safely mapped becomes an obligation, not a deletion.
5. Run a fresh deterministic second pass and require no further diff.
6. Validate restore, package graph, build, test inventory and custom-target behavior before changing the target framework to net10.0.

## Supply-chain rules

Use approved feeds, pinned versions/locks and secret leases. No credential may enter source, logs, argv or durable artifacts. Missing/transitive incompatibility, floating versions, vulnerable or unapproved packages, or a lost custom target blocks promotion.

## Required output

Produce project transformation attribution, package graph diff, preserved-customization inventory, global.json/toolchain manifest, restore/build evidence and idempotence evidence. A syntactically valid csproj is not proof of behavior preservation.
