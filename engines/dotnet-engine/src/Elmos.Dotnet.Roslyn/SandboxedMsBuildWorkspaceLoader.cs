using Elmos.Dotnet.Contracts;
using Microsoft.Build.Locator;
using Microsoft.CodeAnalysis.MSBuild;

namespace Elmos.Dotnet.Roslyn;

public sealed record WorkspaceLoadResult(IReadOnlyList<string> ProjectPaths, IReadOnlyList<string> Diagnostics);

public sealed class SandboxedMsBuildWorkspaceLoader
{
    private readonly RoslynWorkspacePolicy policy = new();

    public async Task<WorkspaceLoadResult> OpenSolutionAsync(
        string approvedWorkspaceRoot,
        string solutionPath,
        RunnerProfile runner,
        bool sandboxed,
        bool networkDenied,
        bool secretsAbsent,
        string configuration,
        CancellationToken cancellationToken)
    {
        if (!policy.CanDynamicallyLoad(runner, sandboxed, networkDenied, secretsAbsent))
            throw new InvalidOperationException("MSBuildWorkspace may load customer projects only in an approved, network-denied Windows sandbox without control-plane secrets.");
        var root = Path.GetFullPath(approvedWorkspaceRoot).TrimEnd(Path.DirectorySeparatorChar);
        var candidate = Path.GetFullPath(solutionPath);
        if (!(candidate.Equals(root, StringComparison.Ordinal) || candidate.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.Ordinal)))
            throw new InvalidOperationException("Solution path escapes the approved workspace root.");
        if (!MSBuildLocator.IsRegistered) MSBuildLocator.RegisterDefaults();
        var properties = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["Configuration"] = configuration,
            ["DesignTimeBuild"] = "true",
            ["BuildingInsideVisualStudio"] = "false",
            ["RestoreIgnoreFailedSources"] = "false"
        };
        using var workspace = MSBuildWorkspace.Create(properties);
        var diagnostics = new List<string>();
        workspace.RegisterWorkspaceFailedHandler(args => diagnostics.Add(args.Diagnostic.ToString()));
        var solution = await workspace.OpenSolutionAsync(candidate, cancellationToken: cancellationToken);
        return new(solution.Projects.Select(project => project.FilePath ?? project.Name).Order(StringComparer.Ordinal).ToArray(), diagnostics);
    }
}
