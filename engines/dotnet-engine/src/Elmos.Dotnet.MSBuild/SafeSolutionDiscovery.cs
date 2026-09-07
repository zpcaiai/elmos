using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml;
using System.Xml.Linq;
using Elmos.Dotnet.Application;
using Elmos.Dotnet.Contracts;
using Elmos.Dotnet.Domain;

namespace Elmos.Dotnet.MSBuild;

public sealed class SafeSolutionDiscovery : ISolutionDiscovery
{
    private static readonly string[] SolutionPatterns = ["*.sln", "*.slnx", "*.slnf"];
    private static readonly string[] ProjectPatterns = ["*.csproj", "*.vbproj", "*.fsproj", "*.vcxproj", "*.sqlproj", "*.shproj", "*.proj"];

    public SolutionInventory Scan(string approvedWorkspaceRoot, string snapshotRef)
    {
        var root = CanonicalRoot(approvedWorkspaceRoot);
        var solutionPaths = SolutionPatterns.SelectMany(pattern => EnumerateFiles(root, pattern)).Order(StringComparer.Ordinal).ToArray();
        var solutions = solutionPaths.Select(path => Relative(root, path)).ToArray();
        var projectPaths = ProjectPatterns.SelectMany(pattern => EnumerateFiles(root, pattern))
            .Distinct(StringComparer.OrdinalIgnoreCase).Order(StringComparer.Ordinal).ToArray();
        var solutionConfigurations = solutionPaths.Where(path => path.EndsWith(".sln", StringComparison.OrdinalIgnoreCase)).SelectMany(ParseSolutionConfigurations).Distinct().ToArray();
        var projects = projectPaths.Select(path => ParseProject(root, path)).Select(project => project with
        {
            Configurations = project.Configurations.Concat(solutionConfigurations.Select(pair => pair.Configuration)).Distinct(StringComparer.OrdinalIgnoreCase).ToArray(),
            Platforms = project.Platforms.Concat(solutionConfigurations.Select(pair => pair.Platform)).Distinct(StringComparer.OrdinalIgnoreCase).ToArray()
        }).ToArray();
        var findings = new List<string>();
        if (solutions.Length == 0) findings.Add("ORPHAN_PROJECT_SET");
        if (solutions.Length > 1) findings.Add("MULTIPLE_SOLUTIONS_AMBIGUOUS");
        if (projects.Length == 0) findings.Add("DOTNET_PROJECT_NOT_FOUND");
        findings.AddRange(projects.SelectMany(p => p.Findings).Distinct(StringComparer.Ordinal));
        return new(snapshotRef, solutions, solutions.Length > 1, projects,
            projects.Where(p => p.LanguageSupport != ProjectLanguageSupport.CSharpFullSupport).Select(p => p.RelativePath).ToArray(), findings);
    }

    private static ProjectInventory ParseProject(string root, string path)
    {
        var document = LoadSafe(path);
        var project = document.Root ?? throw new InvalidDataException($"Project XML has no root: {Relative(root, path)}");
        var sdk = project.Attribute("Sdk")?.Value;
        var oldNamespace = project.Name.NamespaceName.Contains("msbuild", StringComparison.OrdinalIgnoreCase);
        var hasSdkImport = Descendants(project, "Import").Any(e => (e.Attribute("Sdk")?.Value ?? "").Length > 0);
        var format = !string.IsNullOrWhiteSpace(sdk) ? ProjectFormat.SdkStyle : oldNamespace && !hasSdkImport ? ProjectFormat.LegacyNonSdk : hasSdkImport ? ProjectFormat.Hybrid : ProjectFormat.Unknown;
        var findings = new List<string>();
        if (format == ProjectFormat.LegacyNonSdk) findings.Add("LEGACY_PROJECT_FORMAT");
        if (format == ProjectFormat.Hybrid) findings.Add("MIXED_PROJECT_FORMAT");

        var projectDirectory = Path.GetDirectoryName(path)!;
        var references = Descendants(project, "ProjectReference").Select(element =>
        {
            var include = element.Attribute("Include")?.Value ?? "";
            var resolved = Path.GetFullPath(Path.Combine(projectDirectory, include));
            var outside = !IsWithin(root, resolved);
            if (outside) findings.Add("PROJECT_OUTSIDE_REPOSITORY");
            return new ProjectReferenceFact(include.Replace('\\', '/'), Descendants(element, "Project").FirstOrDefault()?.Value, outside);
        }).ToArray();

        var imports = Descendants(project, "Import").Select(e => e.Attribute("Project")?.Value ?? "").Where(v => v.Length > 0).ToArray();
        foreach (var import in imports.Where(i => !i.Contains("$(", StringComparison.Ordinal)))
        {
            var resolved = Path.GetFullPath(Path.Combine(projectDirectory, import));
            if (!IsWithin(root, resolved)) findings.Add("MSBUILD_IMPORT_OUTSIDE_WORKSPACE");
        }
        if (Descendants(project, "UsingTask").Any() || Descendants(project, "Task").Any()) findings.Add("CUSTOM_MSBUILD_TASK");

        var frameworks = Values(project, "TargetFrameworks").SelectMany(v => v.Split(';', StringSplitOptions.RemoveEmptyEntries))
            .Concat(Values(project, "TargetFramework")).Concat(Values(project, "TargetFrameworkVersion"))
            .Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        var configurations = ParseConditionValues(project, "Configuration", "Configurations", ["Debug", "Release"]);
        var platforms = ParseConditionValues(project, "Platform", "Platforms", ["AnyCPU"]);
        var packages = Descendants(project, "PackageReference").Select(e => new PackageFact(
            e.Attribute("Include")?.Value ?? e.Attribute("Update")?.Value ?? "UNKNOWN",
            e.Attribute("Version")?.Value ?? Descendants(e, "Version").FirstOrDefault()?.Value, "PackageReference")).ToList();
        var packagesConfig = Path.Combine(projectDirectory, "packages.config");
        if (File.Exists(packagesConfig))
        {
            var packagesDocument = LoadSafe(packagesConfig);
            packages.AddRange(packagesDocument.Descendants().Where(e => e.Name.LocalName == "package")
                .Select(e => new PackageFact(e.Attribute("id")?.Value ?? "UNKNOWN", e.Attribute("version")?.Value, "packages.config")));
        }
        var languageSupport = LanguageSupport(path);
        if (languageSupport != ProjectLanguageSupport.CSharpFullSupport) findings.Add("UNSUPPORTED_PROJECT_TYPE");
        if (languageSupport == ProjectLanguageSupport.CppCliBlockerAnalysis) findings.Add("CPP_CLI_DEPENDENCY");
        if (Descendants(project, "COMReference").Any()) findings.Add("COM_REFERENCE_PRESENT");
        return new(StableId(Relative(root, path)), Relative(root, path), languageSupport, format, frameworks, configurations, platforms, references, packages, imports, findings.Distinct().ToArray());
    }

    private static XDocument LoadSafe(string path)
    {
        var settings = new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null, MaxCharactersInDocument = 10_000_000 };
        using var stream = File.OpenRead(path);
        using var reader = XmlReader.Create(stream, settings);
        return XDocument.Load(reader, LoadOptions.SetLineInfo);
    }

    private static ProjectLanguageSupport LanguageSupport(string path) => Path.GetExtension(path).ToLowerInvariant() switch
    {
        ".csproj" => ProjectLanguageSupport.CSharpFullSupport,
        ".vbproj" => ProjectLanguageSupport.VisualBasicScanOnly,
        ".fsproj" => ProjectLanguageSupport.FSharpInventoryOnly,
        ".vcxproj" => ProjectLanguageSupport.CppCliBlockerAnalysis,
        ".sqlproj" => ProjectLanguageSupport.SqlProjectInventory,
        _ => ProjectLanguageSupport.UnknownProjectType
    };

    private static IReadOnlyList<string> ParseConditionValues(XElement root, string property, string pluralProperty, string[] defaults)
    {
        var marker = "$(" + property + ")";
        var values = new List<string>(defaults);
        values.AddRange(Values(root, property));
        values.AddRange(Values(root, pluralProperty).SelectMany(value => value.Split(';', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)));
        foreach (var condition in Descendants(root, "PropertyGroup").Select(e => e.Attribute("Condition")?.Value).Where(value => value?.Contains(marker, StringComparison.OrdinalIgnoreCase) == true))
        {
            var equality = condition!.IndexOf("==", StringComparison.Ordinal);
            if (equality < 0) continue;
            var left = condition[..equality];
            var right = condition[(equality + 2)..].Trim().Trim('\'', '"');
            var parts = right.Split('|', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 0) continue;
            if (left.Contains("$(Configuration)", StringComparison.OrdinalIgnoreCase) && left.Contains("$(Platform)", StringComparison.OrdinalIgnoreCase))
            {
                var configurationFirst = left.IndexOf("$(Configuration)", StringComparison.OrdinalIgnoreCase) < left.IndexOf("$(Platform)", StringComparison.OrdinalIgnoreCase);
                var index = property.Equals("Configuration", StringComparison.OrdinalIgnoreCase) == configurationFirst ? 0 : 1;
                if (index < parts.Length) values.Add(parts[index]);
            }
            else values.Add(right);
        }
        return values.Where(value => value.Length is > 0 and < 80).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
    }

    private static IEnumerable<(string Configuration, string Platform)> ParseSolutionConfigurations(string path)
    {
        var inSection = false;
        foreach (var line in File.ReadLines(path))
        {
            if (line.Contains("GlobalSection(SolutionConfigurationPlatforms)", StringComparison.OrdinalIgnoreCase)) { inSection = true; continue; }
            if (inSection && line.Contains("EndGlobalSection", StringComparison.OrdinalIgnoreCase)) yield break;
            if (!inSection) continue;
            var match = Regex.Match(line, "^\\s*([^=|]+)\\|([^=]+?)\\s*=");
            if (match.Success) yield return (match.Groups[1].Value.Trim(), match.Groups[2].Value.Trim());
        }
    }

    private static IEnumerable<XElement> Descendants(XContainer root, string localName) => root.Descendants().Where(e => e.Name.LocalName == localName);
    private static IEnumerable<string> Values(XContainer root, string localName) => Descendants(root, localName).Select(e => e.Value.Trim()).Where(v => v.Length > 0);
    private static string StableId(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant()[..24];
    private static string Relative(string root, string path) => Path.GetRelativePath(root, path).Replace('\\', '/');
    private static bool IsWithin(string root, string path) => path.Equals(root, StringComparison.Ordinal) || path.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.Ordinal);
    private static string CanonicalRoot(string root)
    {
        var canonical = Path.GetFullPath(root);
        if (!Directory.Exists(canonical)) throw new DirectoryNotFoundException(canonical);
        return canonical.TrimEnd(Path.DirectorySeparatorChar);
    }

    private static IEnumerable<string> EnumerateFiles(string root, string pattern)
    {
        var options = new EnumerationOptions { RecurseSubdirectories = true, IgnoreInaccessible = false, AttributesToSkip = FileAttributes.ReparsePoint };
        return Directory.EnumerateFiles(root, pattern, options)
            .Where(path => !Path.GetRelativePath(root, path).Replace('\\', '/').Split('/').Any(part => part is ".git" or ".svn" or "bin" or "obj" or "node_modules" or "packages"))
            .Take(10_000);
    }
}

public static class DynamicMsBuildPolicy
{
    public static bool RequiresSandbox(ProjectInventory project) => project.Imports.Count > 0 || project.Findings.Contains("CUSTOM_MSBUILD_TASK") || project.Format != ProjectFormat.SdkStyle;
    public static RunnerProfile RequiredRunner(ProjectInventory project) => project.TargetFrameworks.Any(f => f.StartsWith("v4", StringComparison.OrdinalIgnoreCase) || f.StartsWith("net4", StringComparison.OrdinalIgnoreCase)) ? RunnerProfile.WindowsLegacy : RunnerProfile.ModernWindows;
}
