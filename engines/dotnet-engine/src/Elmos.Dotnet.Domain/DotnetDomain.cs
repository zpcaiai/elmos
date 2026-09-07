using Elmos.Dotnet.Contracts;

namespace Elmos.Dotnet.Domain;

public enum ProjectLanguageSupport { CSharpFullSupport, VisualBasicScanOnly, FSharpInventoryOnly, CppCliBlockerAnalysis, SqlProjectInventory, UnknownProjectType }
public enum ProjectFormat { LegacyNonSdk, SdkStyle, Hybrid, Unknown }
public enum CompilationState { FullCompilation, PartialCompilation, SyntaxOnly, MetadataOnly, Failed }
public enum Portability { Portable, PortableWithPackage, WindowsOnlySupported, RequiresCompatibilityPack, RequiresAdapter, RequiresRedesign, NoModernEquivalent, Unknown }
public enum TargetStrategy { MinimumSafeFramework, ModernWindows, ModernCrossPlatform, IncrementalSideBySide, StrategicRedesign }
public enum EvidenceStatus { Passed, Failed, Blocked, NotRun, Inconclusive }

public sealed record SourceLocation(string RelativePath, int StartLine, int StartColumn, int EndLine, int EndColumn);
public sealed record ProjectReferenceFact(string Include, string? ProjectGuid, bool OutsideRepository);
public sealed record PackageFact(string Id, string? Version, string Source);
public sealed record ProjectInventory(
    string ProjectId,
    string RelativePath,
    ProjectLanguageSupport LanguageSupport,
    ProjectFormat Format,
    IReadOnlyList<string> TargetFrameworks,
    IReadOnlyList<string> Configurations,
    IReadOnlyList<string> Platforms,
    IReadOnlyList<ProjectReferenceFact> ProjectReferences,
    IReadOnlyList<PackageFact> Packages,
    IReadOnlyList<string> Imports,
    IReadOnlyList<string> Findings);

public sealed record SolutionInventory(
    string SnapshotRef,
    IReadOnlyList<string> Solutions,
    bool PrimarySelectionAmbiguous,
    IReadOnlyList<ProjectInventory> Projects,
    IReadOnlyList<string> UnsupportedProjects,
    IReadOnlyList<string> Findings);

public sealed record TechnologyFinding(
    string FindingId,
    string Technology,
    Portability Portability,
    decimal Confidence,
    string Evidence,
    bool Blocking);

public sealed record TechnologyFingerprint(
    string FingerprintId,
    IReadOnlyList<TechnologyFinding> Findings,
    bool HasDynamicDependencies,
    decimal Confidence,
    IReadOnlyList<string> MigrationBlockers);

public sealed record SymbolNode(
    string SymbolId,
    string Kind,
    string DisplayName,
    string ProjectId,
    SourceLocation? SourceLocation,
    bool GeneratedCode,
    CompilationState CompilationState);

public sealed record SymbolEdge(string FromSymbolId, string ToSymbolId, string Kind, decimal Confidence);
public sealed record RoslynGraph(IReadOnlyList<SymbolNode> Symbols, IReadOnlyList<SymbolEdge> Edges, IReadOnlyList<string> Diagnostics, CompilationState CompilationState);

public sealed record TargetProfile(string ProfileId, TargetStrategy Strategy, string Runtime, string OperatingSystem, string ProjectFormat, string PackageManagement, string Web, string Service, string Data);
public sealed record MigrationStep(string StepId, string StepType, IReadOnlyList<string> ProjectIds, ExecutorType ExecutorType, RunnerProfile RunnerProfile, IReadOnlyList<string> DependsOn, IReadOnlyList<string> Validation, bool RequiresApproval);
public sealed record MigrationPlan(string PlanId, IReadOnlyList<TargetProfile> Candidates, TargetProfile Recommended, IReadOnlyList<MigrationStep> Steps, IReadOnlyList<string> Risks);

public sealed record ValidationObservation(string Gate, EvidenceStatus Status, string EvidenceRef, string Summary);
public sealed record ValidationDecision(EvidenceStatus Status, IReadOnlyList<ValidationObservation> Observations, IReadOnlyList<string> BlockingReasons);

public sealed record UnifiedEvidenceExtension(
    string SchemaVersion,
    string OrganizationId,
    string SnapshotRef,
    string Engine,
    string EngineVersion,
    string ArtifactType,
    string ContentHash,
    EvidenceStatus Status,
    IReadOnlyDictionary<string, object?> Dotnet);
