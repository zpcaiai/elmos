# Batch 11 verification and external gates

## Repository-verifiable scope

The .NET 10 solution provides an independent Worker, safe static SLN/SLNX/SLNF/project discovery, framework/Windows/dynamic-dependency fingerprinting, Roslyn syntax/semantic/IOperation graphing, conservative/balanced/strategic planning, deterministic legacy-project and packages.config modernization, ASP.NET/WCF/EF decision services, an independent validation judge, unified evidence extensions, and tenant-scoped/idempotent job handling.

Java adds only shared Engine Port routing and mixed Java/.NET portfolio aggregation. Flyway V11 adds 61 tenant/RLS-scoped .NET analysis tables but no duplicate workflow, authorization, billing, audit, SCM or delivery tables. C001–C012 are Runtime Skills.

## Local evidence record (2026-07-21)

- `dotnet test engines/dotnet-engine/Elmos.Dotnet.slnx --no-restore`: 11 tests passed, 0 failed/skipped on .NET SDK 10.0.301 / runtime 10.0.9.
- `dotnet restore --locked-mode` reproduced the committed dependency graph, and `dotnet list ... package --vulnerable --include-transitive` reported no vulnerable packages from the configured NuGet sources.
- The Worker started on `127.0.0.1:18086`; capabilities reported `ELMOS_DOTNET`, C#/VB inventory, SLN/SLNX/SLNF and three Runner profiles. A real static scan of `mixed-legacy` returned three content-addressed evidence references, `PARTIAL_COMPILATION`, and `NOT_RUN_REQUIRES_SANDBOXED_WINDOWS_RUNNER` for dynamic MSBuild. Repeating the request returned the same job ID; same-tenant lookup returned HTTP 200 and cross-tenant lookup returned HTTP 404/`POLICY_BLOCKED`.
- `mvn -B verify`: all 38 reactor modules succeeded; 170 tests, 0 failures/errors, 1 skipped. The skip was the Docker-disabled Testcontainers Flyway test.
- Direct PostgreSQL 17 verification compensated for that skip: V1–V11 applied in version order to an ephemeral database; 452 public tables, 451 tenant-isolation policies, 452 `organization_id` columns, and all 61 Batch 11 tables were present. A non-owner role saw exactly one row for either selected tenant, and the `dotnet_build_runs` append-only trigger rejected mutation. The stopped data directory was moved to macOS Trash for recoverable cleanup.
- `pnpm --dir apps/web-console check`: TypeScript and the Next.js 16.2.10 production build passed.
- All five new JSON Schemas passed JSON Schema metaschema validation. Actual Worker fingerprint, Roslyn symbol and evidence-extension payloads validated against their schemas; OpenAPI and Compose YAML parsed successfully.
- All 12 C001–C012 Skills passed skill-creator validation. Three inline adversarial evaluations passed 9/9 assertions; no baseline comparison, token count or timing was fabricated because subagent evaluation was unavailable. The generated static review is under the Skill workspace.
- Registry manifests resolved immutable amd64 digests for the three .NET sandbox bases, but images were not built/scanned/approved; all remain `UNAPPROVED`/`NOT_BUILT`.

## External acceptance gates

1. Build and approve digest-pinned Windows Legacy, Modern Windows and Modern Linux images with SBOM, vulnerability, provenance, secret-scan, toolchain and smoke evidence.
2. On Windows Legacy, load the fixture/customer SLN with real Visual Studio Build Tools and targeting packs; prove all configurations/platforms/imports/tasks and host-parent isolation.
3. Capture an immutable baseline for .NET Framework build, complete test identity, IIS/ASP.NET behavior, WCF clients/contracts, EF schema/query/transaction behavior, COM/native dependencies and bounded performance.
4. Run modern Windows build/test/contract/data validation separately.
5. When cross-platform is selected, run modern Linux build/runtime/platform validation; Windows evidence cannot substitute.
6. Exercise cancellation, lease loss/recovery, stale-attempt rejection, resource limits, default-deny network, secret absence/redaction and evidence upload on real private Runners.
7. Verify YARP/System.Web adapter cutover and exit decision, Web Forms rewrite backlog, custom WCF architecture approval, and EDMX test-database scaffolding.
8. Publish only through existing Draft PR/MR, HEAD-bound checks, signed evidence pack, rollback and human acceptance gates.

## Current environment boundary

The current host is macOS arm64 with .NET 10. It cannot produce Windows Legacy, Visual Studio Build Tools, IIS, COM, Office interop, .NET Framework runtime, WCF legacy-host, or Windows-container evidence. Those states must remain `NOT_RUN`; unapproved image digests remain `BLOCKED`.
