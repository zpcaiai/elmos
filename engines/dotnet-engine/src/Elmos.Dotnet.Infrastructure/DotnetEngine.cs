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

    public EngineJobResponse Scan(EngineJobRequest request) => RunIdempotent(request.OrganizationId, "scan", request.IdempotencyKey, HashInput(request.RepositorySnapshotRef, request.WorkspaceRef, request.Profile, SerializeMap(request.Options)), () =>
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

    public EngineJobResponse Plan(EngineJobRequest request) => RunIdempotent(request.OrganizationId, "plan", request.IdempotencyKey, HashInput(request.RepositorySnapshotRef, request.WorkspaceRef, request.Profile, SerializeMap(request.Options)), () =>
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

    public EngineJobResponse ExecuteStep(ExecuteStepRequest request)
    {
        if (request.StepDefinition is null)
            return Failure("dotnet-invalid-request", DotnetErrorCode.PolicyBlocked, "stepDefinition is required.", "Submit a versioned approved migration step.");
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

    public EngineJobResponse Validate(EngineJobRequest request) => RunIdempotent(request.OrganizationId, "validate", request.IdempotencyKey, HashInput(request.RepositorySnapshotRef, request.WorkspaceRef, request.Profile, SerializeMap(request.Options)), () =>
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

    public EngineJobResponse GetJob(string organizationId, string jobId) => jobs.TryGetValue(jobId, out var stored) && stored.OrganizationId == organizationId ? stored.Response : Failure(jobId, DotnetErrorCode.PolicyBlocked, "Job is not visible in this organization.", "Verify the organization and job identifier.");

    public EngineJobResponse Cancel(string organizationId, string jobId)
    {
        if (!jobs.TryGetValue(jobId, out var stored) || stored.OrganizationId != organizationId) return Failure(jobId, DotnetErrorCode.PolicyBlocked, "Job is not visible in this organization.", "Verify the organization and job identifier.");
        if (stored.Response.Status is JobStatus.Succeeded or JobStatus.Failed or JobStatus.Cancelled)
            return Failure(jobId, DotnetErrorCode.PolicyBlocked, "A terminal job cannot be cancelled or rewritten.", "Retain the historical result and submit a new idempotency key for a new attempt.");
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
                return existing.InputHash == inputHash ? existing.Response : Failure(existingId, DotnetErrorCode.PolicyBlocked, "The idempotency key was already used with different immutable inputs.", "Use the original inputs or submit a new idempotency key.");
            EngineJobResponse response;
            try { response = action(); }
            catch (InvalidOperationException exception) { response = Failure(StableJobId(organizationId, operation, key), DotnetErrorCode.WorkspaceOutsideApprovedRoot, exception.Message, "Use a materialized immutable snapshot inside the approved workspace root."); }
            catch (DirectoryNotFoundException exception) { response = Failure(StableJobId(organizationId, operation, key), DotnetErrorCode.DotnetSolutionNotFound, exception.Message, "Materialize the immutable snapshot before invoking the engine."); }
            catch (Exception exception) { response = Failure(StableJobId(organizationId, operation, key), DotnetErrorCode.InternalEngineError, exception.Message, "Inspect the sanitized engine evidence and retry only if policy permits."); }
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
    private static string StableJobId(string organizationId, string operation, string key) => "dotnet-" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(organizationId + "|" + operation + "|" + key + "|1.0.0"))).ToLowerInvariant()[..24];
    private static string HashInput(params string?[] values) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join("\u001f", values)))).ToLowerInvariant();
    private static string SerializeMap(IReadOnlyDictionary<string, object?>? values) => values is null ? "null" : string.Join("\u001e", values.OrderBy(entry => entry.Key, StringComparer.Ordinal).Select(entry => entry.Key + "=" + (entry.Value is JsonElement element ? element.GetRawText() : JsonSerializer.Serialize(entry.Value))));
    private static void Require(string value, string name) { if (string.IsNullOrWhiteSpace(value)) throw new ArgumentException($"{name} is required", name); }
    private static string ValueAsString(object value) => value is JsonElement element ? element.GetString() ?? element.GetRawText() : value.ToString() ?? "";
    private static string OptionString(IReadOnlyDictionary<string, object?>? options, string key, string fallback) => options is not null && options.TryGetValue(key, out var value) && value is not null ? ValueAsString(value) : fallback;
    private static int OptionInt(IReadOnlyDictionary<string, object?>? options, string key, int fallback) => options is not null && options.TryGetValue(key, out var value) && value is not null ? value is JsonElement e ? e.GetInt32() : Convert.ToInt32(value) : fallback;
    private static bool OptionBool(IReadOnlyDictionary<string, object?>? options, string key) => options is not null && options.TryGetValue(key, out var value) && value is not null && (value is JsonElement e ? e.GetBoolean() : Convert.ToBoolean(value));
}
