namespace Elmos.Dotnet.Contracts;

public enum JobStatus { Accepted, Running, Succeeded, Failed, Cancelled }

public enum RunnerProfile { WindowsLegacy, ModernWindows, ModernLinux }

public enum ExecutorType
{
    Scanner, MsBuildEvaluation, RoslynTransformation, ProjectSystemTransformation,
    AspNetMigration, WcfMigration, EfMigration, BuildTool, TestRunner,
    CodingAgent, ContractChecker, HumanReview
}

public enum DotnetErrorCode
{
    DotnetSolutionNotFound, DotnetMultipleSolutionAmbiguous, MsBuildNotAvailable,
    MsBuildVersionIncompatible, MsBuildEvaluationFailed, VisualStudioComponentMissing,
    TargetingPackMissing, NugetRestoreFailed, RoslynLoadFailed, ProjectTypeUnsupported,
    WindowsRunnerRequired, ModernDotnetRunnerRequired, WorkspaceOutsideApprovedRoot,
    PolicyBlocked, ValidationFailed, InvalidRequest, IdempotencyConflict,
    JobNotFound, JobTerminal, InternalEngineError
}

public sealed record EngineCapabilities(
    string SchemaVersion,
    string Engine,
    string EngineVersion,
    IReadOnlyList<string> Languages,
    IReadOnlyList<string> SolutionFormats,
    IReadOnlyList<string> ProjectFormats,
    IReadOnlyList<string> SourceFrameworks,
    IReadOnlyList<string> MigrationCapabilities,
    IReadOnlyList<RunnerProfile> RunnerProfiles,
    string JobStatePersistence,
    string DurableStateAuthority,
    string RestartRecovery);

public sealed record EngineJobRequest(
    string OrganizationId,
    string RepositorySnapshotRef,
    string WorkspaceRef,
    string Profile,
    string CorrelationId,
    string IdempotencyKey,
    IReadOnlyDictionary<string, object?>? Options = null);

public sealed record ExecutionBudget(long TimeoutSeconds, long CpuSeconds, long MaxBytesWritten, long MaxAgentCredits);
public sealed record StepDefinition(string StepId, ExecutorType ExecutorType, IReadOnlyDictionary<string, object?> Configuration);

public sealed record ExecuteStepRequest(
    string OrganizationId,
    string MigrationRunId,
    int MigrationPlanVersion,
    StepDefinition StepDefinition,
    string WorkspaceRef,
    string SourceCommit,
    ExecutionBudget ExecutionBudget,
    IReadOnlyDictionary<string, object?> Policy,
    string CorrelationId,
    string IdempotencyKey);

public sealed record EngineError(
    DotnetErrorCode ErrorCode,
    string Message,
    bool Retryable,
    IReadOnlyList<string> EvidenceRefs,
    string? FailedCommand,
    string? SanitizedLogRef,
    string SuggestedAction);

public sealed record EngineJobResponse(
    string SchemaVersion,
    string JobId,
    JobStatus Status,
    IReadOnlyList<string> EvidenceRefs,
    IReadOnlyDictionary<string, object?> Result,
    EngineError? Error);

public static class CapabilityManifest
{
    public static EngineCapabilities Current { get; } = new(
        "1.0", "ELMOS_DOTNET", "1.0.0",
        ["C_SHARP", "VISUAL_BASIC_INVENTORY"],
        ["SLN", "SLNX", "SLNF"],
        ["LEGACY_CSPROJ", "SDK_STYLE_CSPROJ", "VBPROJ"],
        ["NET_FRAMEWORK", "NET_CORE", "NET"],
        ["PROJECT_SYSTEM", "ASP_NET", "WCF", "EF6", "ROSLYN", "VALIDATION"],
        [RunnerProfile.WindowsLegacy, RunnerProfile.ModernWindows, RunnerProfile.ModernLinux],
        "EPHEMERAL_PROCESS_LOCAL", "ELMOS_CONTROL_PLANE", "NOT_SUPPORTED_BY_WORKER");
}
