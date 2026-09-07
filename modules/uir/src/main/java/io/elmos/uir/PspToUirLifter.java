package io.elmos.uir;

import io.elmos.semantic.PspModels.*;

import java.time.Clock;
import java.time.Instant;
import java.util.*;

import static io.elmos.uir.UirModels.*;

/** Deterministic PSP-to-UIR lifting. Missing executable semantics become traceable opaque operations. */
public final class PspToUirLifter {
    public static final List<String> PASS_PIPELINE = List.of("declare-lift", "type-lift", "body-lift", "structured-control-flow",
            "evaluation-order-normalization", "cfg-build", "ssa-build", "effect-inference", "exception-model", "async-model",
            "alias-analysis", "canonicalize", "obligation-generation", "conformance-check");
    private static final Set<String> CALLABLE_KINDS = Set.of("method", "function", "constructor", "operator", "delegate", "callable");
    private final UirDialectRegistry dialects; private final Clock clock;

    public PspToUirLifter(UirDialectRegistry dialects, Clock clock) { this.dialects = Objects.requireNonNull(dialects); this.clock = Objects.requireNonNull(clock); }

    public Dataset lift(SemanticDataset psp, io.elmos.semantic.PspModels.ConformanceReport pspReport, LiftProfile profile) {
        Objects.requireNonNull(psp); Objects.requireNonNull(pspReport); Objects.requireNonNull(profile);
        if (pspReport.batch() != 2 || pspReport.status().equals("failed")) throw new IllegalArgumentException("PSP_CONFORMANCE_FAILED");
        String configHash = UirIds.hash(profile, PASS_PIPELINE, dialects.all());
        String runId = UirIds.id("uirrun", psp.manifest().semanticRunId(), configHash);
        Set<String> eligible = new TreeSet<>(); for (io.elmos.semantic.PspModels.ModuleGate gate : pspReport.modules()) if (gate.eligibleForBatch3()) eligible.add(gate.moduleId());
        List<Entity> entities = new ArrayList<>();
        for (String project : psp.manifest().projects().stream().sorted().toList()) {
            if (!eligible.contains(project)) { entities.add(skipped(project, psp, runId)); continue; }
            liftModule(project, psp, runId, profile, entities);
        }
        entities.sort(Comparator.comparing(Entity::entityKind).thenComparing(Entity::entityId));
        Coverage coverage = UirConformanceValidator.coverage(entities, psp);
        List<String> moduleIds = payloads(entities, UirModels.Module.class).stream().map(UirModels.Module::moduleId).sorted().toList();
        List<String> diagnosticIds = payloads(entities, Diagnostic.class).stream().map(Diagnostic::diagnosticId).sorted().toList();
        boolean restricted = !diagnosticIds.isEmpty()
                || payloads(entities, Obligation.class).stream().anyMatch(value -> value.status().equals("open"))
                || payloads(entities, Operation.class).stream().anyMatch(value -> value.opcode().equals("opaque"));
        String status = moduleIds.isEmpty() ? "blocked" : restricted ? "completed_with_restrictions" : "completed";
        RunManifest manifest = new RunManifest(runId, psp.manifest().semanticRunId(), psp.manifest().snapshotId(), status, UirModels.PROTOCOL_VERSION,
                moduleIds, dialects.all().stream().map(Dialect::name).sorted().toList(), PASS_PIPELINE, configHash, coverage, diagnosticIds, clock.instant());
        return new Dataset(manifest, entities);
    }

    private void liftModule(String project, SemanticDataset psp, String runId, LiftProfile profile, List<Entity> out) {
        List<io.elmos.semantic.PspModels.EntityEnvelope> source = psp.entities().stream().filter(entity -> entity.projectId().equals(project)).toList();
        String language = source.stream().map(io.elmos.semantic.PspModels.EntityEnvelope::language).findFirst().orElse("unknown");
        String moduleId = UirIds.id("uirmodule", psp.manifest().snapshotId(), project);
        Map<String,String> typeIds = new HashMap<>(), declarationIds = new HashMap<>();
        payloadEnvelopes(source, TypePayload.class).forEach(entity -> { TypePayload type = (TypePayload) entity.payload(); typeIds.put(type.typeId(), UirIds.id("uirtype", moduleId, type.typeId())); });
        payloadEnvelopes(source, SymbolPayload.class).forEach(entity -> { SymbolPayload symbol = (SymbolPayload) entity.payload(); declarationIds.put(symbol.symbolId(), UirIds.id("uirdecl", moduleId, symbol.symbolId())); });
        String fallbackType = UirIds.id("uirtype", moduleId, "unknown");
        if (!typeIds.containsValue(fallbackType)) out.add(entity("type", fallbackType, psp, runId, moduleId,
                new UirModels.Type(fallbackType, "unknown", "Unknown", null, List.of(), new Nullability("unknown", "unresolved"), null, null, List.of(), null, List.of(), List.of(), "unresolved", 0, Map.of()), provenance("type-lift", List.of(), "fallback unknown type")));
        for (io.elmos.semantic.PspModels.EntityEnvelope envelope : payloadEnvelopes(source, TypePayload.class)) {
            TypePayload sourceType = (TypePayload) envelope.payload(); String id = typeIds.get(sourceType.typeId());
            UirModels.Type type = new UirModels.Type(id, typeKind(sourceType.kind()), sourceType.displayName(), null,
                    mapIds(sourceType.typeArguments(), typeIds, fallbackType), new Nullability(sourceType.nullability(), language + "-native"),
                    numeric(sourceType), absence(sourceType, language), mapIds(sourceType.parameterTypeIds(), typeIds, fallbackType),
                    mapId(sourceType.returnTypeId(), typeIds, null), List.of(), List.of(), sourceType.origin(), sourceType.confidence(), sourceType.languageExtensions());
            out.add(entity("type", id, psp, runId, moduleId, type, provenance("type-lift", List.of(envelope.entityId()), "native type normalized without target mapping")));
            transform(out, psp, runId, moduleId, "type-lift", envelope.entityId(), id, true);
        }
        List<String> moduleDeclarations = new ArrayList<>();
        for (io.elmos.semantic.PspModels.EntityEnvelope envelope : payloadEnvelopes(source, SymbolPayload.class)) {
            SymbolPayload symbol = (SymbolPayload) envelope.payload(); String declarationId = declarationIds.get(symbol.symbolId()); moduleDeclarations.add(declarationId);
            boolean executableBody = CALLABLE_KINDS.contains(symbol.kind()) && hasExecutableBody(symbol);
            String body = executableBody ? UirIds.id("region", declarationId, "structured") : null;
            Declaration declaration = new Declaration(declarationId, symbol.kind(), symbol.name(), symbol.qualifiedName(), declarationIds.get(symbol.containerSymbolId()),
                    symbol.visibility(), symbol.modifiers(), mapId(symbol.typeId(), typeIds, fallbackType), List.of(), symbol.annotations(), body,
                    List.of(symbol.symbolId()), profile.preserveLanguageExtensions() ? symbol.languageExtensions() : Map.of());
            out.add(entity("declaration", declarationId, psp, runId, moduleId, declaration, provenance("declare-lift", List.of(envelope.entityId()), "native declaration preserved")));
            SourceRange range = symbol.declarationSites().isEmpty() ? null : symbol.declarationSites().getFirst().sourceRange();
            sourceMap(out, psp, runId, moduleId, List.of(envelope.entityId(), symbol.symbolId()), List.of(declarationId), "direct", range, 1, List.of());
            transform(out, psp, runId, moduleId, "declare-lift", envelope.entityId(), declarationId, true);
            if (body != null) liftCallable(envelope, symbol, declarationId, body, language, source, typeIds, declarationIds, fallbackType, psp, runId, moduleId, profile, out);
        }
        UirModels.Module module = new UirModels.Module(moduleId, project, language, moduleDeclarations.stream().sorted().toList(),
                out.stream().filter(entity -> entity.moduleId().equals(moduleId) && entity.payload() instanceof Operation).map(entity -> ((Operation) entity.payload()).dialect()).distinct().sorted().toList(), Map.of("sourceProject", project));
        out.add(entity("module", moduleId, psp, runId, moduleId, module, provenance("module-lift", source.stream().filter(entity -> entity.entityKind().equals("file")).map(io.elmos.semantic.PspModels.EntityEnvelope::entityId).toList(), "project boundary preserved")));
    }

    private void liftCallable(io.elmos.semantic.PspModels.EntityEnvelope symbolEnvelope, SymbolPayload symbol, String declarationId, String structuredRegion,
                              String language, List<io.elmos.semantic.PspModels.EntityEnvelope> source, Map<String,String> typeIds,
                              Map<String,String> declarationIds, String fallbackType, SemanticDataset psp, String runId, String moduleId,
                              LiftProfile profile, List<Entity> out) {
        String structuredBlock = UirIds.id("block", structuredRegion, "entry"), cfgRegion = UirIds.id("region", declarationId, "cfg"), cfgBlock = UirIds.id("block", cfgRegion, "entry");
        List<String> operationIds = new ArrayList<>();
        List<io.elmos.semantic.PspModels.EntityEnvelope> calls = payloadEnvelopes(source, CallSitePayload.class).stream()
                .filter(entity -> ((CallSitePayload) entity.payload()).callerSymbolId().equals(symbol.symbolId())).toList();
        for (io.elmos.semantic.PspModels.EntityEnvelope callEnvelope : calls) {
            CallSitePayload call = (CallSitePayload) callEnvelope.payload(); String operationId = UirIds.id("uirop", declarationId, call.callSiteId());
            String dialect = Set.of("dynamic", "reflective", "unresolved", "runtime-discovery", "runtime-generated", "framework-managed", "native", "unknown").contains(call.resolution())
                    || Set.of("dynamic", "reflective", "runtime-discovery", "framework-managed", "native", "unknown").contains(call.dispatchKind())
                    ? "uir.dynamic" : call.dispatchKind().contains("virtual") || call.dispatchKind().contains("interface") ? "uir.object" : "uir.core";
            String opcode = dialect.equals("uir.dynamic") ? "call" : dialect.equals("uir.object") ? call.dispatchKind().contains("interface") ? "interface_call" : "virtual_call" : "call";
            String resultType = mapId(call.returnTypeId(), typeIds, fallbackType), resultValue = UirIds.id("value", operationId, 0), effectId = UirIds.id("effect", operationId, "unknown-call");
            String sourceMapId = sourceMap(out, psp, runId, moduleId, List.of(callEnvelope.entityId(), call.callSiteId()), List.of(operationId), "normalized", call.sourceRange(), call.confidence(), List.of());
            Map<String,Object> attributes = new TreeMap<>(); attributes.put("resolution", call.resolution()); attributes.put("dispatchKind", call.dispatchKind());
            String declaredTarget = declarationIds.get(call.declaredTargetSymbolId()); if (declaredTarget != null) attributes.put("declaredTarget", declaredTarget);
            if (call.declaredTargetSymbolId() != null) attributes.put("sourceDeclaredTarget", call.declaredTargetSymbolId());
            attributes.put("possibleTargets", mapIds(call.possibleTargets(), declarationIds, null));
            attributes.put("sourcePossibleTargets", call.possibleTargets());
            String receiverType = mapId(call.receiverTypeId(), typeIds, null); if (receiverType != null) attributes.put("receiverType", receiverType);
            attributes.put("argumentTypes", mapIds(call.argumentTypeIds(), typeIds, fallbackType));
            if (call.asyncBehavior() != null) attributes.put("asyncBehavior", call.asyncBehavior());
            Operation operation = new Operation(operationId, dialect, opcode, List.of(), List.of(new Result(resultValue, resultType)), attributes, List.of(), List.of(effectId), List.of(sourceMapId),
                    new Evaluation(List.of("receiver", "arguments-in-source-order"), List.of(), false, true), call.confidence());
            out.add(entity("operation", operationId, psp, runId, moduleId, operation, provenance("body-lift", List.of(callEnvelope.entityId()), "call resolution retained")));
            out.add(entity("value", resultValue, psp, runId, moduleId, new Value(resultValue, resultType, new Definition(operationId, 0), List.of(), List.of(), null), provenance("ssa-build", List.of(operationId), "operation result")));
            String effectKind = call.resolution().equals("reflective") ? "reflection" : dialect.equals("uir.dynamic") ? "dynamic-code" : "unknown";
            out.add(entity("effect", effectId, psp, runId, moduleId, new Effect(effectId, effectKind, operationId, "call-target", "unknown", "unknown", true, "program-order", false, "unknown", call.confidence(), List.of(callEnvelope.entityId())), provenance("effect-inference", List.of(callEnvelope.entityId()), "unknown external summary is not pure")));
            out.add(entity("alias", UirIds.id("alias", resultValue), psp, runId, moduleId, new Alias(resultValue, "immutable", "unknown", "unknown", "unknown-alias", "unknown", "unknown", false, .2, List.of(callEnvelope.entityId())), provenance("alias-analysis", List.of(callEnvelope.entityId()), "insufficient heap evidence")));
            if (dialect.equals("uir.dynamic")) obligation(out, psp, runId, moduleId, declarationId, operationId, "dynamic-feature", "Dynamic or unresolved call requires a target strategy and runtime evidence.", "blocking", List.of("differential-test", "manual-review"));
            operationIds.add(operationId);
        }
        // PSP v1 exposes calls and a control-flow summary, not a lossless executable body. Calls alone
        // never prove that assignments, conditions, evaluation order, cleanup, or returns were lifted.
        // Preserve the unrepresented remainder explicitly so a partial body cannot receive an automatic gate.
        String opaqueId = UirIds.id("uirop", declarationId, calls.isEmpty() ? "opaque-body" : "opaque-body-remainder");
        String opaqueEffectId = UirIds.id("effect", opaqueId, "unknown");
        SourceRange opaqueRange = symbol.declarationSites().isEmpty() ? null : symbol.declarationSites().getFirst().sourceRange();
        String opaqueMapId = sourceMap(out, psp, runId, moduleId, List.of(symbolEnvelope.entityId()), List.of(opaqueId), "opaque", opaqueRange, .2, List.of());
        Map<String,Object> opaqueAttributes = new TreeMap<>();
        opaqueAttributes.put("reason", calls.isEmpty() ? "psp-has-no-executable-operation-detail" : "psp-call-sites-do-not-cover-complete-body");
        opaqueAttributes.put("sourceFragmentRefs", List.of(symbolEnvelope.entityId()));
        opaqueAttributes.put("knownCallSiteIds", calls.stream().map(io.elmos.semantic.PspModels.EntityEnvelope::entityId).sorted().toList());
        opaqueAttributes.put("translationStatus", "manual-or-agent");
        Operation opaque = new Operation(opaqueId, "uir.lang." + language, "opaque", List.of(), List.of(), opaqueAttributes, List.of(), List.of(opaqueEffectId), List.of(opaqueMapId), new Evaluation(List.of(), List.of(), false, true), .2);
        out.add(entity("operation", opaqueId, psp, runId, moduleId, opaque, provenance("body-lift", List.of(symbolEnvelope.entityId()), "unrepresented executable semantics preserved as opaque")));
        out.add(entity("effect", opaqueEffectId, psp, runId, moduleId, new Effect(opaqueEffectId, "unknown", opaqueId, "unknown", "unknown", "unknown", true, "program-order", true, "unknown", .2, List.of(symbolEnvelope.entityId())), provenance("effect-inference", List.of(opaqueId), "opaque operation cannot be pure")));
        obligation(out, psp, runId, moduleId, declarationId, opaqueId, "manual-review", "Opaque callable body remainder must be lowered or verified before implementation generation.", "blocking", List.of("manual-review", "differential-test"));
        operationIds.add(opaqueId);
        String returnId = UirIds.id("uirop", declarationId, "return"); operationIds.add(returnId);
        out.add(entity("operation", returnId, psp, runId, moduleId, new Operation(returnId, "uir.core", "return", List.of(), List.of(), Map.of("synthesized", true), List.of(), List.of(), List.of(), new Evaluation(List.of(), List.of(), false, true), .5), provenance("structured-control-flow", List.of(symbolEnvelope.entityId()), "synthesized structural terminator")));
        out.add(entity("block", structuredBlock, psp, runId, moduleId, new Block(structuredBlock, List.of(), operationIds, returnId, true), provenance("structured-control-flow", List.of(declarationId), "structured entry block")));
        if (profile.buildCfg()) buildCfgView(symbol, declarationId, language, source, operationIds, opaqueId, structuredRegion, cfgRegion, cfgBlock, psp, runId, moduleId, out);
        out.add(entity("region", structuredRegion, psp, runId, moduleId, new Region(structuredRegion, "structured", List.of(structuredBlock), structuredBlock, null, profile.buildCfg() ? cfgRegion : null), provenance("structured-control-flow", List.of(declarationId), "generation view")));
        boolean async = symbol.modifiers().stream().anyMatch(value -> value.equals("async"));
        out.add(entity("exception-contract", UirIds.id("exception", declarationId), psp, runId, moduleId, new ExceptionContract(declarationId, List.of(), List.of(), true, List.of(), .2), provenance("exception-model", List.of(symbolEnvelope.entityId()), "unknown throws retained")));
        List<String> callableEffectIds = out.stream().filter(entity -> entity.moduleId().equals(moduleId) && entity.payload() instanceof Effect effect && structuredOperationsContain(operationIds, effect.operationId()))
                .map(entity -> ((Effect) entity.payload()).effectId()).distinct().sorted().toList();
        String effectSummaryId = UirIds.id("effectsummary", declarationId);
        out.add(entity("effect-summary", effectSummaryId, psp, runId, moduleId,
                new EffectSummary(declarationId, callableEffectIds, true, async, true, "unknown", "unknown", .2),
                provenance("effect-inference", callableEffectIds, "callable summary includes unknown opaque-body effects")));
        if (async) {
            TypePayload callableType = payloadEnvelopes(source, TypePayload.class).stream().map(value -> (TypePayload) value.payload()).filter(value -> value.typeId().equals(symbol.typeId())).findFirst().orElse(null);
            String asyncResultType = callableType == null ? fallbackType : mapId(callableType.returnTypeId(), typeIds, fallbackType);
            out.add(entity("async-contract", UirIds.id("async", declarationId), psp, runId, moduleId, new AsyncContract(declarationId, "source-async", asyncResultType, "single", "unknown", true, false, "unknown", "unknown", "exception-or-rejection", "unknown"), provenance("async-model", List.of(symbolEnvelope.entityId()), "source async modifier")));
        }
    }

    private void buildCfgView(SymbolPayload symbol, String declarationId, String language,
                              List<io.elmos.semantic.PspModels.EntityEnvelope> source, List<String> structuredOperations,
                              String opaqueId, String structuredRegion, String cfgRegion, String fallbackCfgBlock,
                              SemanticDataset psp, String runId, String moduleId, List<Entity> out) {
        io.elmos.semantic.PspModels.EntityEnvelope flowEnvelope = payloadEnvelopes(source, ControlFlowPayload.class).stream()
                .filter(entity -> ((ControlFlowPayload) entity.payload()).callableSymbolId().equals(symbol.symbolId())).findFirst().orElse(null);
        if (flowEnvelope == null || ((ControlFlowPayload) flowEnvelope.payload()).blocks().isEmpty()) {
            String returnId = UirIds.id("uirop", declarationId, "return");
            out.add(entity("block", fallbackCfgBlock, psp, runId, moduleId, new Block(fallbackCfgBlock, List.of(), structuredOperations, returnId, true), provenance("cfg-build", List.of(structuredRegion), "derived single-block cfg without native summary")));
            out.add(entity("region", cfgRegion, psp, runId, moduleId, new Region(cfgRegion, "cfg", List.of(fallbackCfgBlock), fallbackCfgBlock, structuredRegion, null), provenance("cfg-build", List.of(structuredRegion), "derived analysis view")));
            return;
        }
        ControlFlowPayload flow = (ControlFlowPayload) flowEnvelope.payload(); Map<String,String> blockIds = new LinkedHashMap<>();
        for (ControlBlock block : flow.blocks()) blockIds.put(block.blockId(), UirIds.id("block", cfgRegion, block.blockId()));
        String entryBlock = blockIds.getOrDefault(flow.entryBlockId(), blockIds.values().iterator().next());
        Map<String,List<ControlEdge>> outgoing = new HashMap<>(); for (ControlEdge edge : flow.edges()) outgoing.computeIfAbsent(edge.fromBlockId(), ignored -> new ArrayList<>()).add(edge);
        Map<String,String> callOperationIds = new HashMap<>();
        for (io.elmos.semantic.PspModels.EntityEnvelope call : payloadEnvelopes(source, CallSitePayload.class)) {
            CallSitePayload payload = (CallSitePayload) call.payload(); if (payload.callerSymbolId().equals(symbol.symbolId())) callOperationIds.put(call.entityId(), UirIds.id("uirop", declarationId, payload.callSiteId()));
        }
        Set<String> assignedCallOperations = new HashSet<>();
        for (io.elmos.semantic.PspModels.EntityEnvelope call : payloadEnvelopes(source, CallSitePayload.class)) {
            CallSitePayload payload = (CallSitePayload) call.payload(); if (!payload.callerSymbolId().equals(symbol.symbolId())) continue;
            if (flow.blocks().stream().anyMatch(block -> contains(block.sourceRange(), payload.sourceRange()))) assignedCallOperations.add(callOperationIds.get(call.entityId()));
        }
        List<String> generatedBlocks = new ArrayList<>();
        for (ControlBlock sourceBlock : flow.blocks()) {
            String blockId = blockIds.get(sourceBlock.blockId()); generatedBlocks.add(blockId); List<String> blockOperations = new ArrayList<>();
            for (io.elmos.semantic.PspModels.EntityEnvelope call : payloadEnvelopes(source, CallSitePayload.class)) {
                CallSitePayload payload = (CallSitePayload) call.payload();
                if (payload.callerSymbolId().equals(symbol.symbolId()) && contains(sourceBlock.sourceRange(), payload.sourceRange())) blockOperations.add(callOperationIds.get(call.entityId()));
            }
            if (blockId.equals(entryBlock)) {
                for (String operationId : structuredOperations) if (!blockOperations.contains(operationId) && (operationId.equals(opaqueId) || callOperationIds.containsValue(operationId) && !assignedCallOperations.contains(operationId))) blockOperations.add(operationId);
                if (!blockOperations.contains(opaqueId)) blockOperations.add(opaqueId);
            }
            List<ControlEdge> edges = outgoing.getOrDefault(sourceBlock.blockId(), List.of()).stream().sorted(Comparator.comparing(ControlEdge::kind).thenComparing(ControlEdge::toBlockId)).toList();
            String terminatorId = UirIds.id("uirop", declarationId, "cfg-terminator", sourceBlock.blockId()); String opcode = edges.isEmpty() ? "return" : edges.size() == 1 ? "branch" : "conditional";
            Map<String,Object> attributes = new TreeMap<>(); attributes.put("synthesized", true); attributes.put("nativeBlockId", sourceBlock.blockId()); attributes.put("sourceStructures", sourceBlock.structures());
            attributes.put("sourceExitKinds", edges.isEmpty() ? flow.exitKinds() : List.of()); attributes.put("successors", edges.stream().map(edge -> blockIds.get(edge.toBlockId())).filter(Objects::nonNull).toList()); attributes.put("edgeKinds", edges.stream().map(ControlEdge::kind).toList());
            out.add(entity("operation", terminatorId, psp, runId, moduleId, new Operation(terminatorId, "uir.core", opcode, List.of(), List.of(), attributes, List.of(), List.of(), List.of(), new Evaluation(List.of(), List.of(), false, true), .7), provenance("cfg-build", List.of(flowEnvelope.entityId()), "native control-flow summary terminator")));
            blockOperations.add(terminatorId);
            out.add(entity("block", blockId, psp, runId, moduleId, new Block(blockId, List.of(), blockOperations, terminatorId, true), provenance("cfg-build", List.of(flowEnvelope.entityId()), "native control-flow block preserved")));
        }
        for (ControlEdge edge : flow.edges()) {
            String from = blockIds.get(edge.fromBlockId()), to = blockIds.get(edge.toBlockId());
            if (from == null || to == null) continue;
            String edgeId = UirIds.id("cfgedge", cfgRegion, edge.fromBlockId(), edge.toBlockId(), edge.kind());
            out.add(entity("cfg-edge", edgeId, psp, runId, moduleId, new CfgEdge(edgeId, from, to, edge.kind(), List.of(), List.of()), provenance("cfg-build", List.of(flowEnvelope.entityId()), "native control-flow edge preserved")));
        }
        out.add(entity("region", cfgRegion, psp, runId, moduleId, new Region(cfgRegion, "cfg", generatedBlocks, entryBlock, structuredRegion, null), provenance("cfg-build", List.of(flowEnvelope.entityId(), structuredRegion), "derived analysis view from PSP control-flow summary")));
    }

    private static boolean contains(SourceRange container, SourceRange nested) {
        return container != null && nested != null && container.fileId().equals(nested.fileId()) && container.startByte() <= nested.startByte() && container.endByte() >= nested.endByte();
    }
    private static boolean structuredOperationsContain(List<String> operations, String operationId) { return operations.contains(operationId); }

    private static Entity skipped(String project, SemanticDataset psp, String runId) {
        String id = UirIds.id("uirdiag", runId, project, "PSP_GATE_NOT_ELIGIBLE");
        return entity("diagnostic", id, psp, runId, project, new Diagnostic(id, "psp-gate", "blocking", project, "PSP module is not eligible for Batch 3 lifting", true, List.of("resolve-batch-2-gate")), provenance("conformance-check", List.of(), "module skipped fail-closed"));
    }
    private static void obligation(List<Entity> out, SemanticDataset psp, String runId, String moduleId, String declarationId, String operationId,
                                   String category, String statement, String severity, List<String> strategies) {
        String id = UirIds.id("obligation", moduleId, declarationId, operationId, category);
        out.add(entity("obligation", id, psp, runId, moduleId, new Obligation(id, category, declarationId, operationId, statement, Map.of(), Map.of(), strategies, severity, "open", List.of(operationId), "obligation-generation"), provenance("obligation-generation", List.of(operationId), "semantic risk converted to a verifiable obligation")));
    }
    private static String sourceMap(List<Entity> out, SemanticDataset psp, String runId, String moduleId, List<String> pspIds, List<String> uirIds,
                                    String kind, SourceRange range, double confidence, List<String> transformations) {
        String id = UirIds.id("uirmap", moduleId, pspIds, uirIds, kind); SourceMap map = new SourceMap(id, pspIds, uirIds, kind, range, confidence, transformations, List.of());
        out.add(entity("source-map", id, psp, runId, moduleId, map, provenance("source-target-provenance", pspIds, "mapping retained"))); return id;
    }
    private static void transform(List<Entity> out, SemanticDataset psp, String runId, String moduleId, String pass, String input, String output, boolean reversible) {
        String id = UirIds.id("transform", runId, pass, input, output); Transformation value = new Transformation(id, pass, "1.0", List.of(input), List.of(output), "preserving", "rule-verified", reversible, true, Map.of());
        out.add(entity("transformation", id, psp, runId, moduleId, value, provenance(pass, List.of(input), "deterministic lifting rule")));
    }
    private static Entity entity(String kind, String id, SemanticDataset psp, String runId, String module, Object payload, UirModels.Provenance provenance) { return new Entity(kind, id, psp.manifest().snapshotId(), psp.manifest().semanticRunId(), runId, module, payload, provenance); }
    private static UirModels.Provenance provenance(String pass, List<String> inputs, String reason) { return new UirModels.Provenance(UirIds.id("uirprov", pass, inputs, reason), pass, "1.0", inputs, List.of(), reason, Instant.EPOCH); }
    private static List<io.elmos.semantic.PspModels.EntityEnvelope> payloadEnvelopes(List<io.elmos.semantic.PspModels.EntityEnvelope> entities, Class<?> type) { return entities.stream().filter(entity -> type.isInstance(entity.payload())).toList(); }
    private static <T> List<T> payloads(List<Entity> entities, Class<T> type) { return entities.stream().map(Entity::payload).filter(type::isInstance).map(type::cast).toList(); }
    private static String mapId(String id, Map<String,String> ids, String fallback) { return id == null ? fallback : ids.getOrDefault(id, fallback); }
    private static List<String> mapIds(List<String> source, Map<String,String> ids, String fallback) { List<String> result = new ArrayList<>(); for (String id : source) { String mapped = mapId(id, ids, fallback); if (mapped != null) result.add(mapped); } return List.copyOf(result); }
    private static String typeKind(String source) { return Set.of("unknown","unresolved","error","dynamic").contains(source) ? source : source == null ? "unknown" : source; }
    private static boolean hasExecutableBody(SymbolPayload symbol) {
        return !symbol.declarationSites().isEmpty()
                && symbol.modifiers().stream().noneMatch(Set.of("abstract", "native", "extern")::contains);
    }
    private static NumericSemantics numeric(TypePayload type) { String name = type.canonicalName() == null ? type.displayName() : type.canonicalName(); if (name == null) return null; String lower = name.toLowerCase(Locale.ROOT); if (!lower.matches(".*(int|long|short|byte|float|double|decimal|bigint|number).*")) return null; return new NumericSemantics(lower.contains("float") || lower.contains("double") || lower.equals("number") ? "floating" : lower.contains("decimal") ? "decimal" : lower.contains("bigint") ? "bigint" : "integer", null, null, null, null, "runtime-dependent", lower.contains("float") || lower.contains("double") || lower.equals("number"), lower.contains("float") || lower.contains("double") || lower.equals("number")); }
    private static AbsenceSemantics absence(TypePayload type, String language) { String name = (type.displayName() == null ? "" : type.displayName()).toLowerCase(Locale.ROOT); if (type.kind().equals("nullable") || name.contains("none") || name.contains("undefined") || name.contains("optional")) { String kind = name.contains("undefined") ? "undefined" : name.contains("none") ? "none-singleton" : name.contains("optional") ? "optional-wrapper-empty" : "null-reference"; return new AbsenceSemantics(kind, !kind.equals("null-reference"), language + "-runtime"); } return null; }
}
