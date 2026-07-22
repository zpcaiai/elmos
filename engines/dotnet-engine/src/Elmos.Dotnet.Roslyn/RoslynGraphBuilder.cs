using System.Security.Cryptography;
using System.Text;
using Elmos.Dotnet.Application;
using Elmos.Dotnet.Contracts;
using Elmos.Dotnet.Domain;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Operations;

namespace Elmos.Dotnet.Roslyn;

public sealed class RoslynGraphBuilder : IRoslynGraphBuilder
{
    public async Task<RoslynGraph> BuildAsync(string approvedWorkspaceRoot, SolutionInventory inventory, CancellationToken cancellationToken)
    {
        var root = Path.GetFullPath(approvedWorkspaceRoot).TrimEnd(Path.DirectorySeparatorChar);
        var symbols = new List<SymbolNode>();
        var edges = new List<SymbolEdge>();
        var diagnostics = new List<string>();
        var enumeration = new EnumerationOptions { RecurseSubdirectories = true, IgnoreInaccessible = false, AttributesToSkip = FileAttributes.ReparsePoint };
        var files = Directory.EnumerateFiles(root, "*.cs", enumeration)
            .Where(path => !Path.GetRelativePath(root, path).Replace('\\', '/').Split('/').Any(part => part is ".git" or ".svn" or "bin" or "obj" or "node_modules" or "packages"))
            .Where(path => new FileInfo(path).Length <= 2_000_000).Take(100_000).Order(StringComparer.Ordinal).ToArray();
        if (files.Length == 0) return new([], [], ["NO_CSHARP_DOCUMENTS"], CompilationState.SyntaxOnly);

        var trees = new List<SyntaxTree>();
        foreach (var path in files)
        {
            var source = await File.ReadAllTextAsync(path, cancellationToken);
            trees.Add(CSharpSyntaxTree.ParseText(source, new CSharpParseOptions(LanguageVersion.Latest), Path.GetRelativePath(root, path).Replace('\\', '/'), cancellationToken: cancellationToken));
        }
        var references = TrustedPlatformReferences();
        var compilation = CSharpCompilation.Create("Elmos.Analysis", trees, references, new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary, allowUnsafe: true));
        var errors = compilation.GetDiagnostics(cancellationToken).Where(d => d.Severity == DiagnosticSeverity.Error).ToArray();
        var state = errors.Length == 0 ? CompilationState.FullCompilation : CompilationState.PartialCompilation;
        diagnostics.AddRange(errors.Take(200).Select(d => d.ToString()));

        foreach (var tree in trees)
        {
            var model = compilation.GetSemanticModel(tree, ignoreAccessibility: true);
            var rootNode = await tree.GetRootAsync(cancellationToken);
            var generated = IsGenerated(tree.FilePath, rootNode);
            foreach (var declaration in rootNode.DescendantNodes().OfType<MemberDeclarationSyntax>())
            {
                var declared = model.GetDeclaredSymbol(declaration, cancellationToken);
                if (declared is null) continue;
                var location = declared.Locations.FirstOrDefault(l => l.IsInSource)?.GetLineSpan();
                symbols.Add(new(StableSymbolId(declared), declared.Kind.ToString().ToUpperInvariant(), declared.ToDisplayString(SymbolDisplayFormat.CSharpErrorMessageFormat),
                    ProjectId(inventory, tree.FilePath), location is null ? null : new(tree.FilePath, location.Value.StartLinePosition.Line + 1, location.Value.StartLinePosition.Character + 1, location.Value.EndLinePosition.Line + 1, location.Value.EndLinePosition.Character + 1), generated, state));
            }
            foreach (var invocation in rootNode.DescendantNodes().OfType<InvocationExpressionSyntax>())
            {
                var operation = model.GetOperation(invocation, cancellationToken) as IInvocationOperation;
                var enclosing = model.GetEnclosingSymbol(invocation.SpanStart, cancellationToken);
                if (operation?.TargetMethod is null || enclosing is null) continue;
                var dispatch = operation.TargetMethod.IsVirtual || operation.TargetMethod.IsAbstract ? "VIRTUAL_DISPATCH" : operation.TargetMethod.ContainingType?.TypeKind == TypeKind.Interface ? "INTERFACE_DISPATCH" : "DIRECT_STATIC_CALL";
                edges.Add(new(StableSymbolId(enclosing), StableSymbolId(operation.TargetMethod), dispatch, dispatch == "DIRECT_STATIC_CALL" ? 0.98m : 0.75m));
            }
        }
        return new(symbols.GroupBy(s => s.SymbolId).Select(g => g.First()).OrderBy(s => s.SymbolId).ToArray(), edges.Distinct().OrderBy(e => e.FromSymbolId).ToArray(), diagnostics, state);
    }

    private static IReadOnlyList<MetadataReference> TrustedPlatformReferences()
    {
        var tpa = AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES") as string;
        return string.IsNullOrWhiteSpace(tpa) ? [MetadataReference.CreateFromFile(typeof(object).Assembly.Location)] : tpa.Split(Path.PathSeparator).Select(path => MetadataReference.CreateFromFile(path)).ToArray();
    }

    private static bool IsGenerated(string path, SyntaxNode root) => path.EndsWith(".designer.cs", StringComparison.OrdinalIgnoreCase) || path.EndsWith(".g.cs", StringComparison.OrdinalIgnoreCase) || path.EndsWith(".generated.cs", StringComparison.OrdinalIgnoreCase) || root.GetLeadingTrivia().ToFullString().Contains("<auto-generated", StringComparison.OrdinalIgnoreCase);
    private static string ProjectId(SolutionInventory inventory, string path) => inventory.Projects.OrderByDescending(p => p.RelativePath.Length).FirstOrDefault(p => path.Contains(Path.GetDirectoryName(p.RelativePath) ?? "", StringComparison.OrdinalIgnoreCase))?.ProjectId ?? "unresolved-project";
    private static string StableSymbolId(ISymbol symbol) => StableId(symbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat) + "|" + symbol.Kind);
    private static string StableId(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant()[..32];
}

public sealed class RoslynWorkspacePolicy
{
    public bool CanDynamicallyLoad(RunnerProfile runner, bool sandboxed, bool networkDenied, bool secretsAbsent) => sandboxed && networkDenied && secretsAbsent && runner is RunnerProfile.WindowsLegacy or RunnerProfile.ModernWindows;
}
