---
name: solution-msbuild-project-discovery
description: Discover SLN, SLNX, SLNF, legacy and SDK-style .NET projects with a safe static phase and an isolated dynamic MSBuild phase.
---

# Solution, MSBuild, and Project Discovery

Use this skill before any .NET target selection or transformation.

## Static phase

Parse solution/project/XML files with DTD and external resolution disabled. Do not execute MSBuild, imports, targets, tasks, restore hooks, analyzers, or generators. Inventory SLN/SLNX/SLNF; csproj, vbproj, fsproj, vcxproj, sqlproj and custom projects; Directory.Build/Packages files; global.json; NuGet files; references; imports; targets; tasks; packages; configurations; platforms; runtime identifiers; and project edges.

Mark C# as full support, VB as scan-only, F# as inventory-only, C++/CLI as blocker analysis, SQL projects as inventory, and unknown types as manual/future engine work. Never silently omit them.

If several solutions exist, return `MULTIPLE_SOLUTIONS_AMBIGUOUS`. Rank candidates only using repository root, CI/build references, project coverage, application projects, documentation and explicit customer selection; never choose the shortest filename.

## Dynamic phase

Run actual MSBuild evaluation only in a leased network-denied sandbox without control-plane secrets. Use the declared configuration/platform and matching SDK/Visual Studio components. Keep the workspace at an isolated filesystem root so host-parent `Directory.Build.props`, `Directory.Build.targets`, or NuGet files cannot contaminate evaluation. Record every resolved import and task assembly.

## Required output

Produce solution inventory, project graph, evaluated properties, import graph, all configuration/platform pairs, and unsupported-project findings. Flag outside-repository references/imports, custom tasks, mixed formats, framework/platform conflicts, missing references, COM, and C++/CLI.

Static results never imply that dynamic evaluation passed. Missing sandbox evidence is `NOT_RUN`, not success.
