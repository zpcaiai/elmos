---
name: b30-dotnet-framework-modernization
description: "Modernize legacy .NET Framework applications to modern .NET, including old project formats, System.Web, ASP.NET MVC/Web API, WCF, Windows services, EF6, configuration, authentication, Windows-only dependencies, tests, and deployment behavior."
---

## Operating mode

Work in the repository. Inspect existing Batch 20-29 modules, contracts, build commands, framework packs, and tests before editing. Implement the smallest production-shaped vertical slice that satisfies this skill; do not stop at a design document when code, manifests, and executable tests can be added.

Read these shared contracts first:

- `../../../docs/batch30/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch30/QUALITY_GATES.md`
- `../../../docs/batch30/REPOSITORY_LAYOUT.md`
- `../../../docs/batch30/VERSION_POLICY.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch30/scaffold_framework_pack.py ...`
- `python3 scripts/batch30/validate_framework_pack.py ...`
- `python3 scripts/batch30/run_framework_gate.py ...`

## Global constraints

- Treat every framework migration pack as directional and version-specific. Reverse migration and version upgrade are separate packs.
- Extract runtime behavior into the framework-neutral Framework Contract Model before generating target code. Do not implement annotation-name substitution as the migration architecture.
- Invoke real source and target build/runtime tools. A generated project that only parses is not evidence of support.
- Preserve authentication, authorization, transaction, persistence, message delivery, configuration precedence, validation, lifecycle, and error contracts.
- Keep development, holdout, and representative-repository corpora physically separate. Do not author rules from holdout cases.
- Prefer deterministic mappings and certified adapters. Model-generated output is a candidate and must pass the same build, contract, behavior, security, and test-integrity gates.
- Record unsupported, conditional, and unknown behavior explicitly. Never hide it with TODOs, permissive stubs, broad exception swallowing, disabled security, or weakened tests.
- Record exact framework/runtime/provider versions, source and target commits, recipe digest, model/prompt versions, toolchain digests, and evidence references.
- Fix repeated failures in the fingerprint, contract model, recipe, adapter, or generator instead of patching many generated files.
- Run the narrowest relevant tests first, then the independent holdout suite and framework certification gate before making release claims.


## Skill 1170: Legacy .NET Framework to modern .NET modernization

Create a certified path from exact .NET Framework application types to modern .NET target profiles such as ASP.NET Core, Worker Service, gRPC, or retained Windows compatibility components.

## Use this skill when

- A customer needs to move from .NET Framework to supported modern .NET.
- A Windows-hosted legacy application uses System.Web, WCF, Windows services, EF6, remoting, COM, registry, GAC, or old project formats.
- An existing modernization pack needs additional application-type coverage.

## Framework-specific risks and invariants

- System.Web lifecycle, HttpContext, modules/handlers, session, authentication, and configuration differ materially from ASP.NET Core.
- WCF bindings, security, transactions, duplex callbacks, and hosting may require gRPC, REST, compatibility, or retained Windows services.
- AppDomain, remoting, registry, COM, Windows identity, and OS APIs may prevent cross-platform migration.
- EF6 and EF Core differ in queries, tracking, migrations, lazy loading, and providers.

## Workflow

1. Inventory solutions/projects, target frameworks, packages.config/NuGet, IIS/System.Web, MVC/Web API, WCF, services, EF6, config, auth, COM/native, registry, file system, and deployment dependencies.
2. Build and run the source with exact MSBuild/runtime/server configuration; capture routes, services, config, security, data, and operations.
3. Extract FCM plus Windows-platform contracts; classify each dependency as modernize, adapter, compatibility, Windows-only, sidecar, replace, or block.
4. Select an exact modern .NET profile and incrementally convert projects, dependencies, hosting, configuration, DI, logging, entrypoints, data, tests, and deployment.
5. Preserve public contracts and introduce facade/strangler boundaries for WCF or Windows-only components that cannot move atomically.
6. Run real target build/startup and behavior tests on the actual target OS/container.
7. Run holdout cases for System.Web lifecycle, WCF bindings, Windows auth, EF6 queries, services, COM/native, and legacy build plugins.
8. Produce platform-dependency, compatibility, deployment, rollback, and retirement evidence.

## Required repository outputs

- `framework-packs/dotnet-framework-to-modern-dotnet/`
- Legacy application and Windows dependency fingerprint
- Modern .NET target profile(s)
- System.Web/WCF/EF6/service mapping plans and recipes
- Compatibility/sidecar/coexistence manifest
- Real source/target build and runtime evidence

## Verification

- Run source MSBuild/runtime and target `dotnet` build/startup.
- Run lifecycle, auth/session, service contract, EF/query/transaction, Windows-service, shutdown, and target-platform tests.
- Verify all cross-platform claims on the actual target platform.
- Run holdout and representative legacy applications.

## Stop and escalate when

- Windows-only dependencies are hidden by stubs or untested assumptions.
- WCF or authentication security is downgraded without approved contract changes.
- EF6 queries are considered migrated because they compile.
- The source cannot be built or required IIS/server configuration is unavailable.

## Definition of done

The modernization pack has exact profiles, explicit Windows and compatibility boundaries, real builds/runtime tests, preserved public/data/security contracts, holdout evidence, and a production transition path.
