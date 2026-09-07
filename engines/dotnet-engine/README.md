# ELMOS .NET Engine

This independent .NET 10 Worker implements the shared `/engine/v1` contract. It owns .NET-specific discovery, technology fingerprinting, Roslyn semantics, planning, deterministic project transformations, and validation normalization. It does not own tenant identity, workflow, billing, audit, SCM, delivery, secrets, or final quality authority.

```bash
dotnet test Elmos.Dotnet.slnx
ELMOS_DOTNET_WORKSPACE_ROOT=/absolute/approved/root \
  dotnet run --project src/Elmos.Dotnet.Worker --urls http://localhost:8086
curl http://localhost:8086/engine/v1/capabilities
```

Static discovery never executes MSBuild. `SandboxedMsBuildWorkspaceLoader` refuses dynamic loading unless its caller proves an approved network-denied Windows sandbox without control-plane secrets. Build/test/IIS/COM/WCF behavior must run on capability-matched external Runners.

The local macOS test suite proves deterministic core behavior only. It is not Windows Legacy, IIS, COM, Visual Studio Build Tools, or Linux-container acceptance evidence.
