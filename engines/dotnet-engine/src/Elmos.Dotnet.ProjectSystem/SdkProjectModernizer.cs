using System.Xml;
using System.Xml.Linq;
using Elmos.Dotnet.Application;
using Elmos.Dotnet.Domain;

namespace Elmos.Dotnet.ProjectSystem;

public sealed class SdkProjectModernizer : IProjectSystemModernizer
{
    public TransformationResult Transform(string projectXml, string? packagesConfig)
    {
        var original = Canonical(projectXml);
        var source = ParseSafe(projectXml);
        var root = StripNamespaces(source.Root ?? throw new InvalidDataException("Project XML has no root element"));
        root.SetAttributeValue("Sdk", root.Attribute("Sdk")?.Value ?? "Microsoft.NET.Sdk");
        root.Attribute("ToolsVersion")?.Remove();
        root.Attribute("DefaultTargets")?.Remove();
        root.Descendants("Import").Where(e => (e.Attribute("Project")?.Value ?? "").Contains("Microsoft.CSharp.targets", StringComparison.OrdinalIgnoreCase)).Remove();
        root.Descendants().Where(e => e.Name.LocalName is "ProjectGuid" or "ProjectTypeGuids" or "TargetFrameworkVersion").Remove();
        var targetProperty = root.Descendants("TargetFramework").FirstOrDefault();
        if (targetProperty is null)
        {
            var propertyGroup = root.Elements("PropertyGroup").FirstOrDefault(e => e.Attribute("Condition") is null) ?? new XElement("PropertyGroup");
            if (propertyGroup.Parent is null) root.AddFirst(propertyGroup);
            propertyGroup.Add(new XElement("TargetFramework", InferFramework(source)));
        }
        var packages = ParsePackages(packagesConfig);
        if (packages.Count > 0)
        {
            var itemGroup = root.Elements("ItemGroup").FirstOrDefault(e => e.Elements("PackageReference").Any()) ?? new XElement("ItemGroup");
            if (itemGroup.Parent is null) root.Add(itemGroup);
            var existing = itemGroup.Elements("PackageReference").Select(e => e.Attribute("Include")?.Value).Where(v => v is not null).ToHashSet(StringComparer.OrdinalIgnoreCase);
            foreach (var package in packages.Where(p => !existing.Contains(p.Id)).OrderBy(p => p.Id, StringComparer.OrdinalIgnoreCase))
                itemGroup.Add(new XElement("PackageReference", new XAttribute("Include", package.Id), package.Version is null ? null : new XAttribute("Version", package.Version)));
            root.Descendants("None").Where(e => string.Equals(e.Attribute("Include")?.Value, "packages.config", StringComparison.OrdinalIgnoreCase)).Remove();
        }
        var preserved = root.Descendants().Where(e => e.Name.LocalName is "Target" or "UsingTask" or "Import").Select(e => e.Name.LocalName + ":" + (e.Attribute("Name")?.Value ?? e.Attribute("Project")?.Value ?? "custom")).ToArray();
        var output = new XDocument(new XDeclaration("1.0", "utf-8", null), root).ToString();
        var second = Canonical(output);
        return new(output, packages, preserved, !string.Equals(original, second, StringComparison.Ordinal), string.Equals(second, Canonical(TransformOnce(output)), StringComparison.Ordinal));
    }

    private static string TransformOnce(string xml)
    {
        var doc = ParseSafe(xml);
        return new XDocument(doc).ToString();
    }

    private static string InferFramework(XDocument source)
    {
        var version = source.Descendants().FirstOrDefault(e => e.Name.LocalName == "TargetFrameworkVersion")?.Value.Trim().ToLowerInvariant();
        return version switch { "v4.8.1" => "net481", "v4.8" => "net48", "v4.7.2" => "net472", "v4.6.2" => "net462", _ => "net48" };
    }

    private static List<PackageFact> ParsePackages(string? content)
    {
        if (string.IsNullOrWhiteSpace(content)) return [];
        var doc = ParseSafe(content);
        return doc.Descendants().Where(e => e.Name.LocalName == "package").Select(e => new PackageFact(e.Attribute("id")?.Value ?? "UNKNOWN", e.Attribute("version")?.Value, "packages.config")).ToList();
    }

    private static XDocument ParseSafe(string xml)
    {
        var settings = new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null, MaxCharactersInDocument = 10_000_000 };
        using var textReader = new StringReader(xml);
        using var reader = XmlReader.Create(textReader, settings);
        return XDocument.Load(reader, LoadOptions.PreserveWhitespace);
    }

    private static XElement StripNamespaces(XElement element) => new(element.Name.LocalName,
        element.Attributes().Where(a => !a.IsNamespaceDeclaration).Select(a => new XAttribute(a.Name.LocalName, a.Value)),
        element.Nodes().Select(n => n is XElement child ? StripNamespaces(child) : n));
    private static string Canonical(string xml) => XDocument.Parse(xml).ToString(SaveOptions.DisableFormatting);
}

public enum ToolAuthority { DeterministicCore, OptionalProvider, DeprecatedLegacyAdapter, LongTailAgent }
public sealed record ModernizationToolAdapter(string Name, ToolAuthority Authority, bool CanSelectTarget, bool CanAcceptRisk, bool CanMerge, IReadOnlyList<string> Capabilities);

public static class ModernizationToolRegistry
{
    public static IReadOnlyList<ModernizationToolAdapter> All { get; } =
    [
        new("ROSLYN", ToolAuthority.DeterministicCore, false, false, false, ["SYMBOL_ANALYSIS", "CODE_FIX", "ATTRIBUTION"]),
        new("GITHUB_COPILOT_MODERNIZATION", ToolAuthority.OptionalProvider, false, false, false, ["ASSESSMENT", "LONG_TAIL_SUGGESTION"]),
        new("UPGRADE_ASSISTANT", ToolAuthority.DeprecatedLegacyAdapter, false, false, false, ["LEGACY_REPORT_IMPORT"]),
        new("CODEX", ToolAuthority.LongTailAgent, false, false, false, ["BOUNDED_REPAIR"]),
        new("CLAUDE_CODE", ToolAuthority.LongTailAgent, false, false, false, ["BOUNDED_REPAIR"]),
        new("OPENHANDS", ToolAuthority.LongTailAgent, false, false, false, ["BOUNDED_REPAIR"])
    ];
}
