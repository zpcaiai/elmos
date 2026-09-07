package io.elmos.semantic;

import java.util.*;

import static io.elmos.semantic.PspModels.*;

public final class SemanticConformanceValidator {
    private static final Set<String> ENTITY_KINDS = Set.of("file", "token", "comment", "syntax-node", "scope", "symbol", "type", "reference",
            "inheritance-edge", "call-site", "call-edge", "control-flow", "source-map", "diagnostic", "metric", "external-dependency");

    public ConformanceReport validate(SemanticDataset dataset) {
        Objects.requireNonNull(dataset); List<String> violations = new ArrayList<>(); Set<String> ids = new HashSet<>();
        Map<String, EntityEnvelope> byId = new HashMap<>(); Map<String, Long> fileBytes = new HashMap<>();
        for (EntityEnvelope entity : dataset.entities()) {
            if (!entity.protocolVersion().equals(PROTOCOL_VERSION)) violations.add("PROTOCOL_VERSION:" + entity.entityId());
            if (!entity.snapshotId().equals(dataset.manifest().snapshotId())) violations.add("SNAPSHOT_MISMATCH:" + entity.entityId());
            if (!entity.semanticRunId().equals(dataset.manifest().semanticRunId())) violations.add("RUN_MISMATCH:" + entity.entityId());
            if (!ENTITY_KINDS.contains(entity.entityKind())) violations.add("ENTITY_KIND_UNKNOWN:" + entity.entityId());
            if (!ids.add(entity.entityId())) violations.add("DUPLICATE_ID:" + entity.entityId()); else byId.put(entity.entityId(), entity);
            if (entity.provenance() == null) violations.add("PROVENANCE_MISSING:" + entity.entityId());
            if (entity.payload() instanceof FilePayload file) fileBytes.put(file.fileId(), file.contentBytes());
        }
        for (EntityEnvelope entity : dataset.entities()) validateEntity(entity, byId, fileBytes, violations);
        List<String> blocking = dataset.entities().stream().filter(entity -> entity.payload() instanceof DiagnosticPayload diagnostic && diagnostic.blocking()).map(EntityEnvelope::entityId).toList();
        List<ModuleGate> gates = dataset.manifest().projects().stream().sorted().map(project -> gate(project, dataset.entities().stream().filter(entity -> entity.projectId().equals(project)).toList(), violations)).toList();
        CoverageMetrics coverage = coverage(dataset.entities()); boolean anyEligible = gates.stream().anyMatch(ModuleGate::eligibleForBatch3);
        String status = !violations.isEmpty() ? "failed" : gates.stream().allMatch(ModuleGate::eligibleForBatch3) ? "passed" : anyEligible ? "passed_with_restrictions" : "blocked";
        List<String> actions = new ArrayList<>(); if (!violations.isEmpty()) actions.add("repair-referential-or-source-integrity");
        if (!blocking.isEmpty()) actions.add("resolve-blocking-semantic-diagnostics");
        if (coverage.symbolResolutionRate() < .90) actions.add("complete-symbol-bindings"); if (coverage.typeResolutionRate() < .85) actions.add("complete-type-environment");
        if (coverage.unresolvedCallRate() > .10) actions.add("improve-call-resolution-or-add-runtime-trace-plan");
        return new ConformanceReport(status, 2, gates, coverage, blocking, violations.stream().distinct().sorted().toList(), actions.stream().distinct().toList());
    }

    static CoverageMetrics coverage(List<EntityEnvelope> entities) {
        long files = count(entities, "file"), parsedFiles = entities.stream().filter(entity -> entity.entityKind().equals("syntax-node") && entity.payload() instanceof SyntaxNodePayload node && node.parentNodeId() == null && !node.errorRecovery()).map(EntityEnvelope::projectId).count();
        List<ReferencePayload> references = payloads(entities, ReferencePayload.class); long resolvedReferences = references.stream().filter(reference -> !Set.of("unresolved", "dynamic", "name-inferred").contains(reference.resolution()) && reference.targetSymbolId() != null).count();
        List<SymbolPayload> symbols = payloads(entities, SymbolPayload.class); Map<String, TypePayload> types = new HashMap<>(); for (TypePayload type : payloads(entities, TypePayload.class)) types.put(type.typeId(), type);
        long typed = symbols.stream().filter(symbol -> symbol.typeId() != null && types.containsKey(symbol.typeId()) && !Set.of("unknown", "unresolved", "error", "dynamic").contains(types.get(symbol.typeId()).kind())).count();
        List<CallSitePayload> calls = payloads(entities, CallSitePayload.class); long exact = calls.stream().filter(call -> Set.of("exact", "compiler-selected").contains(call.resolution())).count();
        long candidates = calls.stream().filter(call -> call.resolution().equals("candidate-set")).count(); long dynamic = calls.stream().filter(call -> Set.of("dynamic", "reflective").contains(call.resolution())).count();
        long unresolved = calls.stream().filter(call -> call.resolution().equals("unresolved")).count();
        Set<String> mapped = new HashSet<>(); for (SourceMapPayload map : payloads(entities, SourceMapPayload.class)) { if (map.symbolId() != null) mapped.add(map.symbolId()); if (map.callSiteId() != null) mapped.add(map.callSiteId()); }
        long mappable = symbols.size() + calls.size();
        return new CoverageMetrics(rate(parsedFiles, files, 0), rate(resolvedReferences, references.size(), 1), rate(typed, symbols.size(), 1), rate(exact, calls.size(), 0),
                rate(candidates, calls.size(), 0), rate(dynamic, calls.size(), 0), rate(unresolved, calls.size(), 0), rate(mapped.size(), mappable, 1));
    }

    private static ModuleGate gate(String project, List<EntityEnvelope> entities, List<String> repositoryViolations) {
        CoverageMetrics coverage = coverage(entities); List<String> restrictions = new ArrayList<>();
        boolean blocking = entities.stream().anyMatch(entity -> entity.payload() instanceof DiagnosticPayload diagnostic && diagnostic.blocking());
        boolean dynamicLanguage = entities.stream().anyMatch(entity -> entity.language().equals("python") || entity.language().equals("javascript"));
        double symbolThreshold = dynamicLanguage ? .70 : .90;
        boolean gateA = coverage.syntaxParseRate() >= .98 && coverage.sourceMapCoverage() >= .99 && coverage.symbolResolutionRate() >= symbolThreshold;
        boolean gateB = gateA && coverage.typeResolutionRate() >= .85 && coverage.unresolvedCallRate() <= .10;
        boolean gateC = gateB && coverage.typeResolutionRate() >= .95 && coverage.symbolResolutionRate() >= .98 && coverage.dynamicCallRate() <= .05 && coverage.sourceMapCoverage() >= .995;
        if (blocking) restrictions.add("blocking-diagnostic"); if (!gateA) restrictions.add("uir-structure-threshold-not-met");
        if (dynamicLanguage && coverage.dynamicCallRate() > .05) restrictions.add("dynamic-language-runtime-evidence-required");
        if (repositoryViolations.stream().anyMatch(value -> value.contains(project) || entities.stream().anyMatch(entity -> value.contains(entity.entityId()))))
            restrictions.add("referential-integrity-failure");
        String gate = gateC ? "C" : gateB ? "B" : gateA ? "A" : "NONE";
        return new ModuleGate(project, gate, gateA && !blocking && restrictions.stream().noneMatch(value -> value.equals("referential-integrity-failure")), gateB && !blocking, restrictions, coverage);
    }

    private static void validateEntity(EntityEnvelope entity, Map<String, EntityEnvelope> byId, Map<String, Long> fileBytes, List<String> violations) {
        Object payload = entity.payload(); SourceRange range = range(payload); if (range != null) validateRange(entity.entityId(), range, fileBytes, violations);
        if (payload instanceof SyntaxNodePayload node) optional(node.parentNodeId(), byId, "PARENT_NODE", entity, violations);
        else if (payload instanceof ScopePayload scope) { optional(scope.parentScopeId(), byId, "PARENT_SCOPE", entity, violations); optional(scope.ownerSymbolId(), byId, "SCOPE_OWNER", entity, violations); }
        else if (payload instanceof SymbolPayload symbol) { required(symbol.scopeId(), byId, "SYMBOL_SCOPE", entity, violations); required(symbol.typeId(), byId, "SYMBOL_TYPE", entity, violations); optional(symbol.containerSymbolId(), byId, "SYMBOL_CONTAINER", entity, violations); for (DeclarationSite site : symbol.declarationSites()) validateRange(entity.entityId(), site.sourceRange(), fileBytes, violations); }
        else if (payload instanceof TypePayload type) { optional(type.returnTypeId(), byId, "RETURN_TYPE", entity, violations); type.typeArguments().forEach(id -> required(id, byId, "TYPE_ARGUMENT", entity, violations)); type.members().forEach(id -> required(id, byId, "TYPE_MEMBER", entity, violations)); }
        else if (payload instanceof ReferencePayload reference) { required(reference.sourceNodeId(), byId, "REFERENCE_NODE", entity, violations); optional(reference.sourceSymbolId(), byId, "REFERENCE_SOURCE", entity, violations); optional(reference.targetSymbolId(), byId, "REFERENCE_TARGET", entity, violations); }
        else if (payload instanceof RelationPayload relation) { required(relation.sourceSymbolId(), byId, "EDGE_SOURCE", entity, violations); required(relation.targetSymbolId(), byId, "EDGE_TARGET", entity, violations); required(relation.sourceNodeId(), byId, "EDGE_NODE", entity, violations); }
        else if (payload instanceof CallSitePayload call) { required(call.callerSymbolId(), byId, "CALL_CALLER", entity, violations); required(call.sourceNodeId(), byId, "CALL_NODE", entity, violations); optional(call.declaredTargetSymbolId(), byId, "CALL_DECLARED_TARGET", entity, violations); call.possibleTargets().forEach(id -> required(id, byId, "CALL_POSSIBLE_TARGET", entity, violations)); optional(call.receiverTypeId(), byId, "CALL_RECEIVER_TYPE", entity, violations); optional(call.returnTypeId(), byId, "CALL_RETURN_TYPE", entity, violations); }
        else if (payload instanceof CallEdgePayload edge) { required(edge.callSiteId(), byId, "CALL_EDGE_SITE", entity, violations); required(edge.callerSymbolId(), byId, "CALL_EDGE_CALLER", entity, violations); required(edge.targetSymbolId(), byId, "CALL_EDGE_TARGET", entity, violations); }
        else if (payload instanceof ControlFlowPayload flow) { required(flow.callableSymbolId(), byId, "CFG_CALLABLE", entity, violations); flow.blocks().forEach(block -> validateRange(entity.entityId(), block.sourceRange(), fileBytes, violations)); }
        else if (payload instanceof SourceMapPayload map) { required(map.nativeNodeId(), byId, "SOURCE_MAP_NODE", entity, violations); optional(map.symbolId(), byId, "SOURCE_MAP_SYMBOL", entity, violations); optional(map.typeId(), byId, "SOURCE_MAP_TYPE", entity, violations); optional(map.referenceId(), byId, "SOURCE_MAP_REFERENCE", entity, violations); optional(map.callSiteId(), byId, "SOURCE_MAP_CALL", entity, violations); }
    }
    private static SourceRange range(Object payload) { if (payload instanceof TokenPayload value) return value.sourceRange(); if (payload instanceof CommentPayload value) return value.sourceRange(); if (payload instanceof SyntaxNodePayload value) return value.sourceRange(); if (payload instanceof ScopePayload value) return value.sourceRange(); if (payload instanceof ReferencePayload value) return value.sourceRange(); if (payload instanceof RelationPayload value) return value.sourceRange(); if (payload instanceof CallSitePayload value) return value.sourceRange(); if (payload instanceof SourceMapPayload value) return value.sourceRange(); if (payload instanceof DiagnosticPayload value) return value.sourceRange(); return null; }
    private static void validateRange(String entity, SourceRange range, Map<String, Long> files, List<String> violations) { Long bytes = files.get(range.fileId()); if (bytes == null) violations.add("SOURCE_FILE_MISSING:" + entity + ":" + range.fileId()); else if (range.endByte() > bytes) violations.add("SOURCE_RANGE_OUT_OF_BOUNDS:" + entity); }
    private static void required(String id, Map<String,EntityEnvelope> byId, String kind, EntityEnvelope source, List<String> violations) { if (id == null || !byId.containsKey(id)) violations.add(kind + "_MISSING:" + source.entityId() + ":" + id); }
    private static void optional(String id, Map<String,EntityEnvelope> byId, String kind, EntityEnvelope source, List<String> violations) { if (id != null) required(id, byId, kind, source, violations); }
    private static long count(List<EntityEnvelope> entities, String kind) { return entities.stream().filter(entity -> entity.entityKind().equals(kind)).count(); }
    private static double rate(long numerator, long denominator, double emptyValue) { return denominator == 0 ? emptyValue : Math.round((numerator / (double) denominator) * 100_000d) / 100_000d; }
    private static <T> List<T> payloads(List<EntityEnvelope> entities, Class<T> type) { return entities.stream().map(EntityEnvelope::payload).filter(type::isInstance).map(type::cast).toList(); }
}
