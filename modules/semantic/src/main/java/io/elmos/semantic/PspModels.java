package io.elmos.semantic;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/** Polyglot Semantic Protocol v1 contracts. Language-specific facts remain in extensions. */
public final class PspModels {
    private PspModels() {}
    public static final String PROTOCOL_VERSION = "1.0";

    public record SourceRange(String fileId, long startByte, long endByte, int startLine, int startColumn,
                              int endLine, int endColumn) {
        public SourceRange {
            require(fileId, "fileId");
            if (startByte < 0 || endByte < startByte || startLine < 1 || endLine < startLine || startColumn < 0 || endColumn < 0)
                throw new IllegalArgumentException("invalid source range");
        }
    }
    public record Provenance(String adapter, String adapterVersion, String provider, String providerVersion,
                             String method, String analysisProfile, String resolution, double confidence,
                             List<String> inputHashes, Instant observedAt) {
        public Provenance {
            require(adapter, "adapter"); require(adapterVersion, "adapterVersion"); require(provider, "provider");
            require(providerVersion, "providerVersion"); require(method, "method"); require(analysisProfile, "analysisProfile");
            require(resolution, "resolution"); if (confidence < 0 || confidence > 1) throw new IllegalArgumentException("confidence outside [0,1]");
            inputHashes = List.copyOf(inputHashes);
        }
    }
    public record EntityEnvelope(String protocolVersion, String entityKind, String entityId, String snapshotId,
                                 String semanticRunId, String projectId, String language, Object payload,
                                 Provenance provenance) {
        public EntityEnvelope {
            require(protocolVersion, "protocolVersion"); require(entityKind, "entityKind"); require(entityId, "entityId");
            require(snapshotId, "snapshotId"); require(semanticRunId, "semanticRunId"); require(projectId, "projectId");
            require(language, "language"); if (payload == null || provenance == null) throw new IllegalArgumentException("payload and provenance are required");
        }
    }

    public record FilePayload(String fileId, String projectId, String path, String language, String contentHash,
                              long contentBytes, String encoding, String lineEnding, String category,
                              boolean generated, boolean test, String parserLevel, boolean fallbackUsed) {}
    public record TokenPayload(String tokenKind, String textHash, SourceRange sourceRange) {}
    public record CommentPayload(String category, String textHash, SourceRange sourceRange, String attachedNodeId) {}
    public record SyntaxNodePayload(String nodeId, String nativeKind, String parentNodeId, SourceRange sourceRange,
                                    boolean errorRecovery, List<String> tokenIds, List<String> commentIds,
                                    Map<String, Object> languageExtensions) {
        public SyntaxNodePayload { tokenIds = List.copyOf(tokenIds); commentIds = List.copyOf(commentIds); languageExtensions = Map.copyOf(languageExtensions); }
    }
    public record ScopePayload(String scopeId, String kind, String parentScopeId, String ownerSymbolId, SourceRange sourceRange) {}
    public record DeclarationSite(String fileId, String nodeId, SourceRange sourceRange) {}
    public record SymbolPayload(String symbolId, String kind, String name, String qualifiedName,
                                String containerSymbolId, String scopeId, String visibility,
                                List<String> modifiers, List<DeclarationSite> declarationSites,
                                String typeId, Map<String, Object> signature, List<String> annotations,
                                boolean publicApi, boolean testSymbol, Map<String, Object> languageExtensions) {
        public SymbolPayload {
            modifiers = List.copyOf(modifiers); declarationSites = List.copyOf(declarationSites);
            signature = Map.copyOf(signature); annotations = List.copyOf(annotations); languageExtensions = Map.copyOf(languageExtensions);
        }
    }
    public record TypePayload(String typeId, String kind, String displayName, String canonicalName,
                              List<String> typeArguments, List<String> members, String returnTypeId,
                              List<String> parameterTypeIds, String nullability, String mutability,
                              String origin, double confidence, Map<String, Object> languageExtensions) {
        public TypePayload {
            typeArguments = List.copyOf(typeArguments); members = List.copyOf(members); parameterTypeIds = List.copyOf(parameterTypeIds);
            languageExtensions = Map.copyOf(languageExtensions); if (confidence < 0 || confidence > 1) throw new IllegalArgumentException("type confidence outside [0,1]");
        }
    }
    public record ReferencePayload(String referenceId, String sourceNodeId, String sourceSymbolId,
                                   String targetSymbolId, String kind, String resolution, double confidence,
                                   SourceRange sourceRange) {}
    public record RelationPayload(String edgeId, String kind, String sourceSymbolId, String targetSymbolId,
                                  String sourceNodeId, String resolution, double confidence, SourceRange sourceRange,
                                  Map<String, Object> languageExtensions) {
        public RelationPayload { languageExtensions = Map.copyOf(languageExtensions); }
    }
    public record CallSitePayload(String callSiteId, String callerSymbolId, String sourceNodeId,
                                  String expressionHash, String dispatchKind, String resolution,
                                  String declaredTargetSymbolId, List<String> possibleTargets,
                                  String receiverTypeId, List<String> argumentTypeIds, String returnTypeId,
                                  String asyncBehavior, double confidence, SourceRange sourceRange,
                                  Map<String, Object> languageExtensions) {
        public CallSitePayload { possibleTargets = List.copyOf(possibleTargets); argumentTypeIds = List.copyOf(argumentTypeIds); languageExtensions = Map.copyOf(languageExtensions); }
    }
    public record CallEdgePayload(String callEdgeId, String callSiteId, String callerSymbolId,
                                  String targetSymbolId, String resolution, double confidence) {}
    public record ControlBlock(String blockId, SourceRange sourceRange, List<String> structures) {
        public ControlBlock { structures = List.copyOf(structures); }
    }
    public record ControlEdge(String fromBlockId, String toBlockId, String kind) {}
    public record ControlFlowPayload(String callableSymbolId, String entryBlockId, List<ControlBlock> blocks,
                                     List<ControlEdge> edges, List<String> exitKinds, Map<String, Boolean> effects,
                                     String nativeCfgRef, List<String> unsupported) {
        public ControlFlowPayload {
            blocks = List.copyOf(blocks); edges = List.copyOf(edges); exitKinds = List.copyOf(exitKinds);
            effects = Map.copyOf(effects); unsupported = List.copyOf(unsupported);
        }
    }
    public record SourceMapPayload(String nativeNodeId, String symbolId, String typeId, String referenceId,
                                   String callSiteId, SourceRange sourceRange, List<String> commentIds) {
        public SourceMapPayload { commentIds = List.copyOf(commentIds); }
    }
    public record DiagnosticPayload(String diagnosticId, String category, String severity, String fileId,
                                    SourceRange sourceRange, String message, String provider, String nativeCode,
                                    List<String> impact, String recommendedAction, double confidence,
                                    boolean blocking) {
        public DiagnosticPayload { impact = List.copyOf(impact); }
    }
    public record MetricPayload(String name, double value, String unit, Map<String, String> dimensions) {
        public MetricPayload { dimensions = Map.copyOf(dimensions); }
    }

    public record AdapterDescriptor(String adapter, String adapterVersion, String language, String provider,
                                    String providerVersion, boolean authoritativeSemantics,
                                    boolean losslessSyntax, String configurationHash) {}
    public record AnalysisProfile(String name, boolean syntax, boolean symbols, boolean types,
                                  boolean callGraph, boolean controlFlow, boolean includeTests) {
        public static AnalysisProfile full() { return new AnalysisProfile("full", true, true, true, true, true, true); }
    }
    public record ResourceBudget(int cpu, int memoryMb, int timeoutSeconds) {
        public ResourceBudget { if (cpu < 1 || memoryMb < 128 || timeoutSeconds < 1) throw new IllegalArgumentException("resource budget must be positive"); }
    }
    public record SemanticRunManifest(String semanticRunId, String snapshotId, String status,
                                      List<AdapterDescriptor> adapters, List<String> projects,
                                      List<String> artifacts, CoverageMetrics metrics,
                                      List<String> diagnosticIds, String configurationHash,
                                      Instant createdAt) {
        public SemanticRunManifest {
            adapters = List.copyOf(adapters); projects = List.copyOf(projects); artifacts = List.copyOf(artifacts); diagnosticIds = List.copyOf(diagnosticIds);
        }
    }
    public record CoverageMetrics(double syntaxParseRate, double symbolResolutionRate,
                                  double typeResolutionRate, double exactCallResolutionRate,
                                  double candidateCallResolutionRate, double dynamicCallRate,
                                  double unresolvedCallRate, double sourceMapCoverage) {}
    public record SemanticDataset(SemanticRunManifest manifest, List<EntityEnvelope> entities) {
        public SemanticDataset { entities = List.copyOf(entities); }
    }
    public record ModuleGate(String moduleId, String gate, boolean eligibleForBatch3,
                             boolean eligibleForAutoTranslation, List<String> restrictions,
                             CoverageMetrics coverage) {
        public ModuleGate { restrictions = List.copyOf(restrictions); }
    }
    public record ConformanceReport(String status, int batch, List<ModuleGate> modules,
                                    CoverageMetrics coverage, List<String> blockingDiagnosticIds,
                                    List<String> violations, List<String> recommendedActions) {
        public ConformanceReport {
            modules = List.copyOf(modules); blockingDiagnosticIds = List.copyOf(blockingDiagnosticIds);
            violations = List.copyOf(violations); recommendedActions = List.copyOf(recommendedActions);
        }
    }

    private static void require(String value, String name) { if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required"); }
}
