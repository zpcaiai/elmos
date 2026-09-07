using Elmos.Dotnet.Contracts;
using Elmos.Dotnet.Domain;

namespace Elmos.Dotnet.Application;

public sealed class ConservativeMigrationPlanner : IMigrationPlanner
{
    public MigrationPlan Plan(SolutionInventory inventory, TechnologyFingerprint fingerprint, RoslynGraph graph, string policy)
    {
        var windowsOnly = fingerprint.Findings.Any(f => f.Portability is Portability.WindowsOnlySupported or Portability.NoModernEquivalent);
        var webForms = fingerprint.Findings.Any(f => f.Technology is "ASP_NET_WEB_FORMS" or "ASP_NET_SYSTEM_WEB");
        var customWcf = fingerprint.Findings.Any(f => f.Technology == "WCF_CUSTOM_BINDING");
        var hasEf = fingerprint.Findings.Any(f => f.Technology.StartsWith("ENTITY_FRAMEWORK", StringComparison.Ordinal) || f.Technology == "EF6_EDMX");
        var candidates = new List<TargetProfile>
        {
            new("conservative", TargetStrategy.MinimumSafeFramework, ".NET Framework 4.8.1", "WINDOWS", "SDK_STYLE", "PACKAGE_REFERENCE", "UNCHANGED", "UNCHANGED", "EF6"),
            new("balanced-windows", TargetStrategy.ModernWindows, ".NET 10", "WINDOWS", "SDK_STYLE", "PACKAGE_REFERENCE", webForms ? "INCREMENTAL_ASPNET_CORE" : "ASP_NET_CORE", customWcf ? "ARCHITECTURE_DECISION" : "COREWCF_CANDIDATE", hasEf ? "EF6_TRANSITION_THEN_EF_CORE" : "UNCHANGED"),
            new("strategic-cross-platform", TargetStrategy.ModernCrossPlatform, ".NET 10", "LINUX_OR_WINDOWS", "SDK_STYLE", "PACKAGE_REFERENCE", webForms ? "REWRITE_REQUIRED" : "ASP_NET_CORE", customWcf ? "REDESIGN" : "COREWCF_GRPC_OR_REST", hasEf ? "EF_CORE_PER_CONTEXT" : "UNCHANGED")
        };
        if (webForms) candidates.Add(new("incremental-side-by-side", TargetStrategy.IncrementalSideBySide, ".NET 10 + .NET Framework", "WINDOWS", "MIXED_TRANSITION", "PACKAGE_REFERENCE", "YARP_AND_SYSTEM_WEB_ADAPTERS", "COEXISTENCE", "EF6_SIDE_BY_SIDE"));

        var requested = policy.ToUpperInvariant();
        var recommended = requested switch
        {
            "CONSERVATIVE" => candidates[0],
            "STRATEGIC" when !windowsOnly && !webForms => candidates[2],
            _ when webForms => candidates.First(c => c.Strategy == TargetStrategy.IncrementalSideBySide),
            _ => candidates[1]
        };
        if (recommended.Strategy == TargetStrategy.ModernCrossPlatform && windowsOnly) recommended = candidates[1];

        var projectIds = inventory.Projects.Select(p => p.ProjectId).ToArray();
        var steps = new List<MigrationStep>
        {
            new("dotnet-baseline-windows", "BASELINE", projectIds, ExecutorType.BuildTool, RunnerProfile.WindowsLegacy, [], ["BUILD", "TEST_INVENTORY"], true),
            new("project-system", "SDK_AND_PACKAGE_REFERENCE", projectIds, ExecutorType.ProjectSystemTransformation, RunnerProfile.ModernWindows, ["dotnet-baseline-windows"], ["IDEMPOTENCE", "NUGET_GRAPH", "NET48_BUILD"], false)
        };
        if (webForms) steps.Add(new("aspnet-incremental", "YARP_SYSTEM_WEB_ADAPTER", projectIds, ExecutorType.AspNetMigration, RunnerProfile.ModernWindows, ["project-system"], ["HTTP_CONTRACT", "SESSION", "AUTH"], true));
        if (fingerprint.Findings.Any(f => f.Technology.StartsWith("WCF", StringComparison.Ordinal))) steps.Add(new("wcf-transition", customWcf ? "WCF_ARCHITECTURE_DECISION" : "COREWCF_CANDIDATE", projectIds, ExecutorType.WcfMigration, RunnerProfile.ModernWindows, ["project-system"], ["WSDL", "SOAP", "SECURITY", "TRANSACTION"], customWcf));
        if (hasEf) steps.Add(new("ef-transition", "EF6_THEN_EFCORE_PER_CONTEXT", projectIds, ExecutorType.EfMigration, RunnerProfile.ModernWindows, ["project-system"], ["SCHEMA", "QUERY", "TRANSACTION"], true));
        var transformationDependencies = steps.Where(s => s.StepId is not "dotnet-baseline-windows" and not "project-system").Select(s => s.StepId).DefaultIfEmpty("project-system").ToArray();
        steps.Add(new("roslyn-fixes", "DETERMINISTIC_ROSLYN", projectIds, ExecutorType.RoslynTransformation, RunnerProfile.ModernWindows, transformationDependencies, ["COMPILATION", "TRANSFORMATION_ATTRIBUTION", "IDEMPOTENCE"], false));
        steps.Add(new("modern-windows-validation", "MIGRATED_WINDOWS", projectIds, ExecutorType.ContractChecker, RunnerProfile.ModernWindows, ["roslyn-fixes"], ["BUILD", "TEST", "CONTRACT", "PERFORMANCE"], false));
        if (recommended.OperatingSystem.Contains("LINUX", StringComparison.Ordinal)) steps.Add(new("modern-linux-validation", "MIGRATED_LINUX", projectIds, ExecutorType.ContractChecker, RunnerProfile.ModernLinux, ["modern-windows-validation"], ["BUILD", "TEST", "PLATFORM", "RUNTIME"], false));
        return new("dotnet-plan-" + fingerprint.FingerprintId, candidates, recommended, steps, fingerprint.MigrationBlockers.Concat(graph.Diagnostics.Take(10)).Distinct().ToArray());
    }
}
