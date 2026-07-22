---
name: dotnet-build-contract-and-behavior-validator
description: Independently compare legacy Windows baseline, modern Windows, and modern Linux .NET results across build, tests, contracts, data, platform, and performance.
---

# .NET Build, Contract, and Behavior Validator

This is a quality-judge skill. It must be independent from Roslyn transformations, modernization tools and coding agents, and it must not modify code.

## Environments

Keep `WINDOWS_LEGACY_BASELINE`, `MODERN_WINDOWS_MIGRATED`, and `MODERN_LINUX_MIGRATED` separate with pinned toolchains, configuration/platform, dependencies and snapshot/commit. A Windows pass cannot substitute for Linux when cross-platform is the target. An unexecuted environment is `NOT_RUN`.

## Gates

Compare build diagnostics and artifacts; discovered/executed/passed/failed/skipped test identity; public API and serialization; ASP.NET HTTP/auth/session; WCF WSDL/SOAP/security/transaction/client behavior; EF schema/SQL/query/transaction/concurrency; Windows/platform analyzers and runtime probes; deployment/startup; and bounded performance/resource measures.

If baseline discovers 800 tests and migrated discovers 240, fail the test gate even if all 240 pass. Missing tests, contracts, fixtures or required environments never count as success. Compare expected baseline limitations separately from migration regressions.

## Required output

Produce environment manifests, normalized build/test/contract/platform/data/performance observations, differences with provenance, and a versioned aggregate decision of `PASSED`, `FAILED`, `BLOCKED`, `NOT_RUN`, or `INCONCLUSIVE`. Only the independent policy version may decide promotion.
