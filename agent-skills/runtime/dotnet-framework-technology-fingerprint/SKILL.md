---
name: dotnet-framework-technology-fingerprint
description: Build an evidence-backed .NET Framework and Windows technology fingerprint that separates modern Windows viability from cross-platform portability.
---

# .NET Framework Technology Fingerprint

Use this skill after project discovery and before target selection.

## Analyze

Combine project/framework metadata, assembly/package references, Roslyn symbol usage, platform analyzer findings, runtime/deployment configuration, and bounded source/config scans. Inventory ASP.NET/Web Forms/MVC/Web API/System.Web; WCF/ASMX/Remoting; EF6/EDMX/LINQ-to-SQL/ADO.NET; Registry, services, event log, performance counters, DirectoryServices, Windows identity, Office/COM/PInvoke/C++/CLI, AppDomain, BinaryFormatter, and similar platform APIs.

Classify each finding as `PORTABLE`, `PORTABLE_WITH_PACKAGE`, `WINDOWS_ONLY_SUPPORTED`, `REQUIRES_COMPATIBILITY_PACK`, `REQUIRES_ADAPTER`, `REQUIRES_REDESIGN`, `NO_MODERN_EQUIVALENT`, or `UNKNOWN`. Windows Compatibility Pack is a transition option, never proof of cross-platform support.

Detect `Assembly.Load`, `LoadFrom`, `Type.GetType`, `Activator.CreateInstance`, MEF/plugin directories, AppDomain, and configuration-selected types. Mark these `DYNAMIC_DEPENDENCY`, lower confidence, and create validation obligations.

## Required output

Produce technology fingerprint, framework usage, Windows dependency inventory, portability findings, dynamic-dependency findings, and migration blockers. Every framework/support assertion needs a source. Do not turn vendor support status into a migration recommendation.

Fail closed when binary-only dependencies, COM/native artifacts, dynamic loading, missing targeting packs, or unresolved project types prevent a trustworthy conclusion.
