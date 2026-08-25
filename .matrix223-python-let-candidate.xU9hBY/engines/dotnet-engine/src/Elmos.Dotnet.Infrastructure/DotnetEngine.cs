using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Elmos.Dotnet.Application;
using Elmos.Dotnet.Contracts;
using Elmos.Dotnet.Domain;
using Elmos.Dotnet.MSBuild;
using Elmos.Dotnet.ProjectSystem;
using Elmos.Dotnet.Roslyn;
using Elmos.Dotnet.Validation;

namespace Elmos.Dotnet.Infrastructure;

public sealed class DotnetEngine : IDotnetEngine
{
    private sealed record StoredJob(string OrganizationId, string IdempotencyScope, string InputHash, EngineJobResponse Response);
    private readonly string approvedWorkspaceRoot;
    private readonly ISolutionDiscovery discovery;
    private readonly ITechnologyFingerprinter fingerprinter;
    private readonly IRoslynGraphBuilder graphBuilder;
    private readonly IMigrationPlanner planner;
    private readonly IProjectSystemModernizer projectSystem;
    private readonly IValidationJudge judge;
    private readonly UnifiedEvidenceMapper evidenceMapper;
    private readonly ConcurrentDictionary<string, StoredJob> jobs = new(StringComparer.Ordinal);
    private readonly ConcurrentDictionary<string, string> idempotency = new(StringComparer.Ordinal);
    private readonly object jobLock = new();

    public DotnetEngine(string approvedWorkspaceRoot)
        : this(approvedWorkspaceRoot, new SafeSolutionDiscovery(), new TechnologyFingerprinter(), new RoslynGraphBuilder(), new ConservativeMigrationPlanner(), new SdkProjectModernizer(), new DotnetValidationJudge(), new UnifiedEvidenceMapper()) { }

    public DotnetEngine(string approvedWorkspaceRoot, ISolutionDiscovery discovery, ITechnologyFingerprinter fingerprinter, IRoslynGraphBuilder graphBuilder, IMigrationPlanner planner, IProjectSystemModernizer projectSystem, IValidationJudge judge, UnifiedEvidenceMapper evidenceMapper)
    {
        this.approvedWorkspaceRoot = Path.GetFullPath(approvedWorkspaceRoot).TrimEnd(Path.DirectorySeparatorChar);
        Directory.CreateDirectory(this.approvedWorkspaceRoot);
        this.discovery = discovery;
        this.fingerprinter = fingerprinter;
        this.graphBuilder = graphBuilder;
        this.planner = planner;
        this.projectSystem = projectSystem;
        this.judge = judge;
        this.evidenceMapper = evidenceMapper;
    }

    public EngineCapabilities Capabilities() => CapabilityManifest.Current;

    public EngineJobResponse Scan(EngineJobRequest request)
    {
        var invalid = ValidateJobRequest(request);
        if (invalid is not null) return InvalidRequest(invalid);
        return RunIdempotent(request.OrganizationId, "scan", request.IdempotencyKey, HashInput(request.RepositorySnapshotRef, request.WorkspaceRef, request.Profile, SerializeMap(request.Options)), () =>
        {
        var workspace = ResolveWorkspace(request.WorkspaceRef);
        var inventory = discovery.Scan(workspace, request.RepositorySnapshotRef);
        var fingerprint = fingerprinter.Fingerprint(workspace, inventory);
        var graph = graphBuilder.BuildAsync(workspace, inventory, CancellationToken.None).GetAwaiter().GetResult();
        var artifacts = new[]
        {
            evidenceMapper.Map(request.OrganizationId, request.RepositorySnapshotRef, "DOTNET_SOLUTION_INVENTORY", inventory, EvidenceStatus.Passed),
            evidenceMapper.Map(request.OrganizationId, request.RepositorySnapshotRef, "DOTNET_TECHNOLOGY_FINGERPRINT", fingerprint, EvidenceStatus.Passed),
            evidenceMapper.Map(request.OrganizationId, request.RepositorySnapshotRef, "ROSLYN_SYMBOL_GRAPH", graph, graph.CompilationState == CompilationState.FullCompilation ? EvidenceStatus.Passed : EvidenceStatus.Inconclusive)
        };
        return Success(StableJobId(request.OrganizationId, "scan", request.IdempotencyKey), artifacts.Select(a => "sha256:" + a.ContentHash).ToArray(), new Dictionary<string, object?>
        {
            ["solutionInventory"] = inventory,
            ["technologyFingerprint"] = fingerprint,
            ["roslynGraph"] = graph,
            ["evidenceExtensions"] = artifacts,
            ["dynamicMsBuildEvaluation"] = "NOT_RUN_REQUIRES_SANDBOXED_WINDOWS_RUNNER"
        });
        });
    }

    public EngineJobResponse Plan(EngineJobRequest request)
    {
        var invalid = ValidateJobRequest(request);
        if (invalid is not null) return InvalidRequest(invalid);
        return RunIdempotent(request.OrganizationId, "plan", request.IdempotencyKey, HashInput(request.RepositorySnapshotRef, request.WorkspaceRef, request.Profile, SerializeMap(request.Options)), () =>
        {
        var workspace = ResolveWorkspace(request.WorkspaceRef);
        var inventory = discovery.Scan(workspace, request.RepositorySnapshotRef);
        var fingerprint = fingerprinter.Fingerprint(workspace, inventory);
        var graph = graphBuilder.BuildAsync(workspace, inventory, CancellationToken.None).GetAwaiter().GetResult();
        var policy = OptionString(request.Options, "policy", "BALANCED");
        var plan = planner.Plan(inventory, fingerprint, graph, policy);
        var evidence = evidenceMapper.Map(request.OrganizationId, request.RepositorySnapshotRef, "DOTNET_MIGRATION_PLAN", plan, plan.Risks.Count == 0 ? EvidenceStatus.Passed : EvidenceStatus.Inconclusive);
        return Success(StableJobId(request.OrganizationId, "plan", request.IdempotencyKey), ["sha256:" + evidence.ContentHash], new Dictionary<string, object?> { ["plan"] = plan, ["evidenceExtension"] = evidence });
        });
    }

    public EngineJobResponse ExecuteStep(ExecuteStepRequest request)
    {
        var invalid = ValidateExecuteRequest(request);
        if (invalid is not null) return InvalidRequest(invalid);
        return RunIdempotent(request.OrganizationId, "execute", request.IdempotencyKey, HashInput(
            request.MigrationRunId, request.MigrationPlanVersion.ToString(), request.StepDefinition.StepId,
            request.StepDefinition.ExecutorType.ToString(), request.WorkspaceRef, request.SourceCommit,
            request.ExecutionBudget.TimeoutSeconds.ToString(), request.ExecutionBudget.CpuSeconds.ToString(),
            request.ExecutionBudget.MaxBytesWritten.ToString(), request.ExecutionBudget.MaxAgentCredits.ToString(),
            SerializeMap(request.StepDefinition.Configuration), SerializeMap(request.Policy)), () =>
        {
            var jobId = StableJobId(request.OrganizationId, "execute", request.IdempotencyKey);
            if (request.StepDefinition.ExecutorType == ExecutorType.ProjectSystemTransformation && request.StepDefinition.Configuration.TryGetValue("projectXml", out var xmlValue) && xmlValue is not null)
            {
                var xml = ValueAsString(xmlValue);
                var packages = request.StepDefinition.Configuration.TryGetValue("packagesConfig", out var packagesValue) && packagesValue is not null ? ValueAsString(packagesValue) : null;
                var result = projectSystem.Transform(xml, packages);
                var evidence = evidenceMapper.Map(request.OrganizationId, request.SourceCommit, "PROJECT_FILE_TRANSFORMATION", result, result.Idempotent ? EvidenceStatus.Passed : EvidenceStatus.Failed);
                var output = new Dictionary<string, object?> { ["transformation"] = result, ["evidenceExtension"] = evidence };
                return result.Idempotent
                    ? Success(jobId, ["sha256:" + evidence.ContentHash], output)
                    : new("1.0", jobId, JobStatus.Failed, ["sha256:" + evidence.ContentHash], output,
                        new(DotnetErrorCode.ValidationFailed, "Project-system transformation was not idempotent.", false,
                            ["sha256:" + evidence.ContentHash], null, null, "Do not apply the patch; inspect and fix the deterministic transformer."));
            }
            return Failure(jobId, DotnetErrorCode.PolicyBlocked, "This step requires a leased Windows/Linux Runner or the external Agent Gateway; no in-process fallback is permitted.", "Route the step through the capability-matched ELMOS Runner.");
        });
    }

    public EngineJobResponse Validate(EngineJobRequest request)
    {
        var invalid = ValidateJobRequest(request);
        if (invalid is not null) return InvalidRequest(invalid);
        return RunIdempotent(request.OrganizationId, "validate", request.IdempotencyKey, HashInput(request.RepositorySnapshotRef, request.WorkspaceRef, request.Profile, SerializeMap(request.Options)), () =>
        {
        var input = new ValidationInput(
            OptionInt(request.Options, "baselineTests", 0), OptionInt(request.Options, "migratedTests", 0),
            OptionBool(request.Options, "baselineWindowsPassed"), OptionBool(request.Options, "migratedWindowsPassed"),
            OptionBool(request.Options, "linuxRequired"), OptionBool(request.Options, "migratedLinuxPassed"), []);
        var decision = judge.Judge(input);
        var evidence = evidenceMapper.Map(request.OrganizationId, request.RepositorySnapshotRef, "DOTNET_VALIDATION_DECISION", decision, decision.Status);
        var jobId = StableJobId(request.OrganizationId, "validate", request.IdempotencyKey);
        return decision.Status == EvidenceStatus.Passed
            ? Success(jobId, ["sha256:" + evidence.ContentHash], new Dictionary<string, object?> { ["decision"] = decision, ["evidenceExtension"] = evidence })
            : new("1.0", jobId, JobStatus.Failed, ["sha256:" + evidence.ContentHash], new Dictionary<string, object?> { ["decision"] = decision, ["evidenceExtension"] = evidence }, new(DotnetErrorCode.ValidationFailed, "Independent .NET validation gates did not pass.", false, ["sha256:" + evidence.ContentHash], null, null, "Resolve failed or missing gates; do not promote the migration."));
        });
    }

    public EngineJobResponse GetJob(string organizationId, string jobId) => jobs.TryGetValue(jobId, out var stored) && stored.OrganizationId == organizationId ? stored.Response : Failure(jobId, DotnetErrorCode.JobNotFound, "The requested engine job was not found.", "Verify the organization and job identifier.");

    public EngineJobResponse Cancel(string organizationId, string jobId)
    {
        if (!jobs.TryGetValue(jobId, out var stored) || stored.OrganizationId != organizationId) return Failure(jobId, DotnetErrorCode.JobNotFound, "The requested engine job was not found.", "Verify the organization and job identifier.");
        if (stored.Response.Status is JobStatus.Succeeded or JobStatus.Failed or JobStatus.Cancelled)
            return Failure(jobId, DotnetErrorCode.JobTerminal, "A terminal job cannot be cancelled or rewritten.", "Retain the historical result and submit a new idempotency key for a new attempt.");
        var cancelled = stored.Response with { Status = JobStatus.Cancelled };
        jobs[jobId] = stored with { Response = cancelled };
        return cancelled;
    }

    private EngineJobResponse RunIdempotent(string organizationId, string operation, string key, string inputHash, Func<EngineJobResponse> action)
    {
        lock (jobLock)
        {
            if (string.IsNullOrWhiteSpace(organizationId) || string.IsNullOrWhiteSpace(key))
                return Failure("dotnet-invalid-request", DotnetErrorCode.PolicyBlocked, "organizationId and idempotencyKey are required.", "Provide a server-derived organization and stable idempotency key.");
            var scope = organizationId + "|" + operation + "|" + key;
            if (idempotency.TryGetValue(scope, out var existingId) && jobs.TryGetValue(existingId, out var existing))
                return existing.InputHash == inputHash ? existing.Response : Failure(existingId, DotnetErrorCode.IdempotencyConflict, "The idempotency key was already used with different immutable inputs.", "Use the original inputs or submit a new idempotency key.");
            EngineJobResponse response;
            try { response = action(); }
            catch (InvalidOperationException) { response = Failure(StableJobId(organizationId, operation, key), DotnetErrorCode.WorkspaceOutsideApprovedRoot, "The workspace request was rejected by the approved-root policy.", "Use a materialized immutable snapshot inside the approved workspace root."); }
            catch (DirectoryNotFoundException) { response = Failure(StableJobId(organizationId, operation, key), DotnetErrorCode.DotnetSolutionNotFound, "The requested .NET workspace or solution was not found.", "Materialize the immutable snapshot before invoking the engine."); }
            catch (Exception) { response = Failure(StableJobId(organizationId, operation, key), DotnetErrorCode.InternalEngineError, "The .NET engine failed without recording successful execution.", "Inspect the sanitized engine evidence and retry only if policy permits."); }
            var stored = new StoredJob(organizationId, scope, inputHash, response);
            jobs[response.JobId] = stored;
            idempotency[scope] = response.JobId;
            return response;
        }
    }

    private string ResolveWorkspace(string workspaceRef)
    {
        Require(workspaceRef, nameof(workspaceRef));
        var candidate = Path.GetFullPath(Path.IsPathRooted(workspaceRef) ? workspaceRef : Path.Combine(approvedWorkspaceRoot, workspaceRef));
        if (!(candidate.Equals(approvedWorkspaceRoot, StringComparison.Ordinal) || candidate.StartsWith(approvedWorkspaceRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal))) throw new InvalidOperationException("Workspace path escapes the approved root.");
        return candidate;
    }

    private static EngineJobResponse Success(string id, IReadOnlyList<string> refs, IReadOnlyDictionary<string, object?> result) => new("1.0", id, JobStatus.Succeeded, refs, result, null);
    private static EngineJobResponse Failure(string id, DotnetErrorCode code, string message, string action) => new("1.0", id, JobStatus.Failed, [], new Dictionary<string, object?>(), new(code, message, false, [], null, null, action));
    private static EngineJobResponse InvalidRequest(string reason) => Failure("dotnet-invalid-request", DotnetErrorCode.InvalidRequest, reason, "Correct the request contract before retrying.");
    private static string? ValidateJobRequest(EngineJobRequest? request)
    {
        if (request is null) return "A request body is required.";
        if (string.IsNullOrWhiteSpace(request.OrganizationId) || string.IsNullOrWhiteSpace(request.RepositorySnapshotRef)
            || string.IsNullOrWhiteSpace(request.WorkspaceRef) || string.IsNullOrWhiteSpace(request.Profile)
            || string.IsNullOrWhiteSpace(request.CorrelationId) || string.IsNullOrWhiteSpace(request.IdempotencyKey))
            return "All required job request fields must be non-blank.";
        return null;
    }
    private static string? ValidateExecuteRequest(ExecuteStepRequest? request)
    {
        if (request is null) return "A request body is required.";
        if (string.IsNullOrWhiteSpace(request.OrganizationId) || string.IsNullOrWhiteSpace(request.MigrationRunId)
            || string.IsNullOrWhiteSpace(request.WorkspaceRef) || string.IsNullOrWhiteSpace(request.SourceCommit)
            || string.IsNullOrWhiteSpace(request.CorrelationId) || string.IsNullOrWhiteSpace(request.IdempotencyKey))
            return "All required execute-step fields must be non-blank.";
        if (request.MigrationPlanVersion <= 0) return "migrationPlanVersion must be positive.";
        if (request.StepDefinition is null || string.IsNullOrWhiteSpace(request.StepDefinition.StepId)
            || request.StepDefinition.Configuration is null) return "A complete stepDefinition is required.";
        if (request.ExecutionBudget is null) return "executionBudget is required.";
        if (request.ExecutionBudget.TimeoutSeconds <= 0 || request.ExecutionBudget.CpuSeconds <= 0
            || request.ExecutionBudget.MaxBytesWritten < 0 || request.ExecutionBudget.MaxAgentCredits < 0)
            return "Execution budget values are outside the allowed range.";
        if (request.Policy is null) return "policy is required.";
        return null;
    }
    private static string StableJobId(string organizationId, string operation, string key) => "dotnet-" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(organizationId + "|" + operation + "|" + key + "|1.0.0"))).ToLowerInvariant()[..24];
    private static string HashInput(params string?[] values) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Concat(values.Select(value => LengthPrefix(value ?? "")))))).ToLowerInvariant();
    private static string SerializeMap(IReadOnlyDictionary<string, object?>? values) => values is null || values.Count == 0 ? "" : string.Concat(values.OrderBy(entry => entry.Key, StringComparer.Ordinal).Select(entry => LengthPrefix(entry.Key) + LengthPrefix(SerializeValue(entry.Value))));
    private static string SerializeValue(object? value) => value switch
    {
        null => "null",
        JsonElement element => SerializeElement(element),
        IReadOnlyDictionary<string, object?> map => "M" + SerializeMap(map),
        IEnumerable<object?> items => "L" + string.Concat(items.Select(item => LengthPrefix(SerializeValue(item)))),
        _ => JsonSerializer.Serialize(value)
    };
    private static string SerializeElement(JsonElement element) => element.ValueKind switch
    {
        JsonValueKind.Object => "M" + string.Concat(element.EnumerateObject().OrderBy(property => property.Name, StringComparer.Ordinal).Select(property => LengthPrefix(property.Name) + LengthPrefix(SerializeElement(property.Value)))),
        JsonValueKind.Array => "L" + string.Concat(element.EnumerateArray().Select(item => LengthPrefix(SerializeElement(item)))),
        JsonValueKind.String => JsonSerializer.Serialize(element.GetString()),
        JsonValueKind.Null => "null",
        _ => element.GetRawText()
    };
    private static string LengthPrefix(string value) => value.Length + ":" + value;
    private static void Require(string value, string name) { if (string.IsNullOrWhiteSpace(value)) throw new ArgumentException($"{name} is required", name); }
    private static string ValueAsString(object value) => value is JsonElement element ? element.GetString() ?? element.GetRawText() : value.ToString() ?? "";
    private static string OptionString(IReadOnlyDictionary<string, object?>? options, string key, string fallback) => options is not null && options.TryGetValue(key, out var value) && value is not null ? ValueAsString(value) : fallback;
    private static int OptionInt(IReadOnlyDictionary<string, object?>? options, string key, int fallback) => options is not null && options.TryGetValue(key, out var value) && value is not null ? value is JsonElement e ? e.GetInt32() : Convert.ToInt32(value) : fallback;
    private static bool OptionBool(IReadOnlyDictionary<string, object?>? options, string key) => options is not null && options.TryGetValue(key, out var value) && value is not null && (value is JsonElement e ? e.GetBoolean() : Convert.ToBoolean(value));
}
