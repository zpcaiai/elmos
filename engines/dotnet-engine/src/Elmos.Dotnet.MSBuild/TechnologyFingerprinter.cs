using System.Security.Cryptography;
using System.Text;
using Elmos.Dotnet.Application;
using Elmos.Dotnet.Domain;

namespace Elmos.Dotnet.MSBuild;

public sealed class TechnologyFingerprinter : ITechnologyFingerprinter
{
    private static readonly (string Token, string Technology, Portability Portability, bool Blocking)[] Signatures =
    [
        ("System.Web", "ASP_NET_SYSTEM_WEB", Portability.RequiresRedesign, true),
        (".aspx", "ASP_NET_WEB_FORMS", Portability.RequiresRedesign, true),
        ("ServiceContract", "WCF", Portability.RequiresAdapter, false),
        ("CustomBinding", "WCF_CUSTOM_BINDING", Portability.RequiresRedesign, true),
        ("System.Data.Entity", "ENTITY_FRAMEWORK_6", Portability.RequiresAdapter, false),
        (".edmx", "EF6_EDMX", Portability.RequiresRedesign, true),
        ("Microsoft.Win32.Registry", "WINDOWS_REGISTRY", Portability.WindowsOnlySupported, true),
        ("Microsoft.Win32", "WINDOWS_REGISTRY", Portability.WindowsOnlySupported, true),
        ("ServiceController", "WINDOWS_SERVICE", Portability.WindowsOnlySupported, true),
        ("DllImport", "PINVOKE", Portability.WindowsOnlySupported, true),
        ("COMReference", "COM", Portability.NoModernEquivalent, true),
        ("Office.Interop", "OFFICE_INTEROP", Portability.WindowsOnlySupported, true),
        ("BinaryFormatter", "BINARY_FORMATTER", Portability.RequiresRedesign, true),
        ("System.Drawing", "SYSTEM_DRAWING", Portability.WindowsOnlySupported, false),
        ("Assembly.Load", "DYNAMIC_DEPENDENCY", Portability.Unknown, true),
        ("Assembly.LoadFrom", "DYNAMIC_DEPENDENCY", Portability.Unknown, true),
        ("Type.GetType", "DYNAMIC_DEPENDENCY", Portability.Unknown, true),
        ("Activator.CreateInstance", "DYNAMIC_DEPENDENCY", Portability.Unknown, true)
    ];

    public TechnologyFingerprint Fingerprint(string approvedWorkspaceRoot, SolutionInventory inventory)
    {
        var root = Path.GetFullPath(approvedWorkspaceRoot).TrimEnd(Path.DirectorySeparatorChar);
        var candidates = Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
            .Where(path => !IsExcluded(root, path))
            .Where(path => new[] { ".cs", ".config", ".csproj", ".edmx", ".aspx", ".svc" }.Contains(Path.GetExtension(path), StringComparer.OrdinalIgnoreCase))
            .Where(path => new FileInfo(path).Length <= 2_000_000)
            .Take(100_000);
        var findings = new List<TechnologyFinding>();
        foreach (var path in candidates)
        {
            var content = File.ReadAllText(path);
            var relative = Path.GetRelativePath(root, path).Replace('\\', '/');
            foreach (var signature in Signatures.Where(s => content.Contains(s.Token, StringComparison.OrdinalIgnoreCase) || relative.Contains(s.Token, StringComparison.OrdinalIgnoreCase)))
            {
                var id = StableId($"{relative}:{signature.Technology}:{signature.Token}");
                findings.Add(new(id, signature.Technology, signature.Portability, signature.Technology == "DYNAMIC_DEPENDENCY" ? 0.55m : 0.9m, $"{relative}:{signature.Token}", signature.Blocking));
            }
        }
        foreach (var project in inventory.Projects)
        {
            foreach (var framework in project.TargetFrameworks.Where(f => f.Contains("4", StringComparison.OrdinalIgnoreCase)))
                findings.Add(new(StableId(project.ProjectId + framework), "NET_FRAMEWORK", Portability.RequiresCompatibilityPack, 0.98m, $"{project.RelativePath}:{framework}", false));
            foreach (var package in project.Packages.Where(p => p.Id.StartsWith("EntityFramework", StringComparison.OrdinalIgnoreCase)))
                findings.Add(new(StableId(project.ProjectId + package.Id), "ENTITY_FRAMEWORK_6", Portability.RequiresAdapter, 0.96m, $"{project.RelativePath}:{package.Id}", false));
        }
        var distinct = findings.GroupBy(f => f.FindingId).Select(g => g.First()).OrderBy(f => f.FindingId).ToArray();
        var dynamic = distinct.Any(f => f.Technology == "DYNAMIC_DEPENDENCY");
        return new(StableId(inventory.SnapshotRef + string.Join('|', distinct.Select(f => f.FindingId))), distinct, dynamic, dynamic ? 0.7m : 0.93m,
            distinct.Where(f => f.Blocking).Select(f => f.Technology).Distinct().Order().ToArray());
    }

    private static string StableId(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant()[..24];
    private static bool IsExcluded(string root, string path)
    {
        var relative = Path.GetRelativePath(root, path).Replace('\\', '/');
        return relative.Split('/').Any(part => part is ".git" or ".svn" or "bin" or "obj" or "node_modules" or "packages");
    }
}
