using Elmos.Dotnet.Contracts;
using Elmos.Dotnet.Domain;

namespace Elmos.Dotnet.Application;

public interface ISolutionDiscovery { SolutionInventory Scan(string approvedWorkspaceRoot, string snapshotRef); }
public interface ITechnologyFingerprinter { TechnologyFingerprint Fingerprint(string approvedWorkspaceRoot, SolutionInventory inventory); }
public interface IRoslynGraphBuilder { Task<RoslynGraph> BuildAsync(string approvedWorkspaceRoot, SolutionInventory inventory, CancellationToken cancellationToken); }
public interface IMigrationPlanner { MigrationPlan Plan(SolutionInventory inventory, TechnologyFingerprint fingerprint, RoslynGraph graph, string policy); }
public interface IProjectSystemModernizer { TransformationResult Transform(string projectXml, string? packagesConfig); }
public interface IValidationJudge { ValidationDecision Judge(ValidationInput input); }

public sealed record TransformationResult(string ProjectXml, IReadOnlyList<PackageFact> Packages, IReadOnlyList<string> PreservedCustomizations, bool Changed, bool Idempotent);
public sealed record ValidationInput(int BaselineTests, int MigratedTests, bool BaselineWindowsPassed, bool MigratedWindowsPassed, bool LinuxRequired, bool MigratedLinuxPassed, IReadOnlyList<ValidationObservation> ContractObservations);

public interface IDotnetEngine
{
    EngineCapabilities Capabilities();
    EngineJobResponse Scan(EngineJobRequest request);
    EngineJobResponse Plan(EngineJobRequest request);
    EngineJobResponse ExecuteStep(ExecuteStepRequest request);
    EngineJobResponse Validate(EngineJobRequest request);
    EngineJobResponse GetJob(string organizationId, string jobId);
    EngineJobResponse Cancel(string organizationId, string jobId);
}
