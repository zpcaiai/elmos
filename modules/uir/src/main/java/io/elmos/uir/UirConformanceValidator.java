package io.elmos.uir;

import io.elmos.semantic.PspModels.CallSitePayload;
import io.elmos.semantic.PspModels.EntityEnvelope;
import io.elmos.semantic.PspModels.FilePayload;
import io.elmos.semantic.PspModels.SemanticDataset;
import io.elmos.semantic.PspModels.SourceRange;
import io.elmos.semantic.PspModels.SymbolPayload;
import io.elmos.semantic.PspModels.TypePayload;

import java.util.*;

import static io.elmos.uir.UirModels.*;

/** Structural, referential, provenance, flow, and per-module gate validation for UIR v1. */
public final class UirConformanceValidator {
    private static final Map<Class<?>,String> PAYLOAD_KINDS = Map.ofEntries(
            Map.entry(UirModels.Module.class, "module"), Map.entry(Declaration.class, "declaration"),
            Map.entry(UirModels.Type.class, "type"), Map.entry(Operation.class, "operation"),
            Map.entry(Region.class, "region"), Map.entry(Block.class, "block"), Map.entry(Value.class, "value"),
            Map.entry(CfgEdge.class, "cfg-edge"), Map.entry(Effect.class, "effect"),
            Map.entry(EffectSummary.class, "effect-summary"),
            Map.entry(ExceptionContract.class, "exception-contract"), Map.entry(AsyncContract.class, "async-contract"),
            Map.entry(Alias.class, "alias"), Map.entry(Obligation.class, "obligation"),
            Map.entry(SourceMap.class, "source-map"), Map.entry(Transformation.class, "transformation"),
            Map.entry(Diagnostic.class, "diagnostic"));
    private static final Set<String> TERMINATORS = Set.of("return", "branch", "conditional", "throw", "rethrow", "yield");
    private static final Set<String> CALLABLE_KINDS = Set.of("method", "function", "constructor", "operator", "delegate", "callable");
    private static final Set<String> BODYLESS_MODIFIERS = Set.of("abstract", "native", "extern");

    private final UirDialectRegistry dialects;
    public UirConformanceValidator(UirDialectRegistry dialects) { this.dialects = Objects.requireNonNull(dialects); }

    public ConformanceReport validate(Dataset dataset, SemanticDataset psp) {
        Objects.requireNonNull(dataset); Objects.requireNonNull(psp);
        List<String> violations = new ArrayList<>(); Map<String,Entity> byId = new HashMap<>();
        Set<String> pspIds = new HashSet<>(); Map<String,Long> fileBytes = new HashMap<>();
        for (EntityEnvelope source : psp.entities()) {
            pspIds.add(source.entityId());
            if (source.payload() instanceof FilePayload file) fileBytes.put(file.fileId(), file.contentBytes());
        }
        if (!dataset.manifest().snapshotId().equals(psp.manifest().snapshotId())) violations.add("MANIFEST_PSP_SNAPSHOT_MISMATCH");
        if (!dataset.manifest().semanticRunId().equals(psp.manifest().semanticRunId())) violations.add("MANIFEST_PSP_RUN_MISMATCH");
        if (!dataset.manifest().protocolVersion().equals(PROTOCOL_VERSION)) violations.add("UIR_PROTOCOL_VERSION_UNSUPPORTED:" + dataset.manifest().protocolVersion());
        for (Entity entity : dataset.entities()) {
            if (!entity.snapshotId().equals(dataset.manifest().snapshotId())) violations.add("SNAPSHOT_MISMATCH:" + entity.entityId());
            if (!entity.semanticRunId().equals(dataset.manifest().semanticRunId())) violations.add("SEMANTIC_RUN_MISMATCH:" + entity.entityId());
            if (!entity.uirRunId().equals(dataset.manifest().uirRunId())) violations.add("UIR_RUN_MISMATCH:" + entity.entityId());
            if (entity.provenance() == null) violations.add("PROVENANCE_MISSING:" + entity.entityId());
            if (entity.contentHash() == null || entity.contentHash().isBlank()) violations.add("CONTENT_HASH_MISSING:" + entity.entityId());
            if (entity.generation() < 1) violations.add("GENERATION_INVALID:" + entity.entityId());
            String expectedKind = entity.payload() == null ? null : PAYLOAD_KINDS.get(entity.payload().getClass());
            if (!Objects.equals(expectedKind, entity.entityKind())) violations.add("ENTITY_KIND_PAYLOAD_MISMATCH:" + entity.entityId());
            if (byId.putIfAbsent(entity.entityId(), entity) != null) violations.add("DUPLICATE_ID:" + entity.entityId());
        }
        Set<String> blockArguments = new HashSet<>(); payloads(dataset.entities(), Block.class).forEach(block -> blockArguments.addAll(block.argumentValueIds()));
        for (Entity entity : dataset.entities()) validateEntity(entity, byId, pspIds, fileBytes, blockArguments, violations);
        validateDominance(dataset.entities(), byId, violations);
        for (String moduleId : dataset.manifest().modules()) requiredKind(moduleId, "module", byId, null, "MANIFEST_MODULE", violations);
        for (UirModels.Module module : payloads(dataset.entities(), UirModels.Module.class))
            if (!dataset.manifest().modules().contains(module.moduleId())) violations.add("MODULE_NOT_IN_MANIFEST:" + module.moduleId());

        Coverage actualCoverage = coverage(dataset.entities(), psp);
        if (!actualCoverage.equals(dataset.manifest().coverage())) violations.add("MANIFEST_COVERAGE_STALE");
        List<Diagnostic> blockingDiagnostics = payloads(dataset.entities(), Diagnostic.class).stream().filter(Diagnostic::blocking).toList();
        List<Obligation> open = payloads(dataset.entities(), Obligation.class).stream().filter(value -> !Set.of("verified", "waived").contains(value.status())).toList();
        Map<String,UirModels.Module> modulesByProject = new HashMap<>();
        payloads(dataset.entities(), UirModels.Module.class).forEach(module -> modulesByProject.put(module.projectId(), module));
        List<ModuleGate> gates = new ArrayList<>();
        for (String project : psp.manifest().projects().stream().sorted().toList()) {
            UirModels.Module module = modulesByProject.get(project); String moduleId = module == null ? project : module.moduleId();
            List<Entity> moduleEntities = dataset.entities().stream().filter(entity -> entity.moduleId().equals(moduleId)).toList();
            gates.add(gate(moduleId, moduleEntities, coverage(moduleEntities, subset(psp, project)), violations));
        }
        boolean any = gates.stream().anyMatch(ModuleGate::eligibleForSkeletonGeneration);
        String status = !violations.isEmpty() ? "failed" : gates.isEmpty() ? "blocked"
                : gates.stream().allMatch(ModuleGate::eligibleForSkeletonGeneration) && blockingDiagnostics.isEmpty()
                ? gates.stream().allMatch(ModuleGate::eligibleForAutomaticTranslation) ? "passed" : "passed_with_restrictions"
                : any ? "passed_with_restrictions" : "blocked";
        List<String> actions = new ArrayList<>();
        if (!violations.isEmpty()) actions.add("repair-uir-integrity");
        if (!blockingDiagnostics.isEmpty()) actions.add("resolve-blocking-uir-diagnostics");
        if (actualCoverage.opaqueOperationRate() > .03) actions.add("lower-or-plan-opaque-operations");
        if (actualCoverage.typeCoverage() < .90) actions.add("improve-type-lifting");
        if (actualCoverage.effectCoverage() < .90) actions.add("complete-effect-summaries");
        return new ConformanceReport(3, status, gates, actualCoverage, blockingDiagnostics.stream().map(Diagnostic::diagnosticId).sorted().toList(),
                open.stream().map(Obligation::obligationId).sorted().toList(), violations.stream().distinct().sorted().toList(), actions.stream().distinct().toList());
    }

    static Coverage coverage(List<Entity> entities, SemanticDataset psp) {
        List<EntityEnvelope> sourceSymbolEntities = psp.entities().stream().filter(value -> value.payload() instanceof SymbolPayload).toList();
        List<SymbolPayload> sourceSymbols = sourceSymbolEntities.stream().map(value -> (SymbolPayload) value.payload()).toList();
        List<EntityEnvelope> sourceTypeEntities = psp.entities().stream().filter(value -> value.payload() instanceof TypePayload).toList();
        List<CallSitePayload> sourceCalls = psp.entities().stream().map(EntityEnvelope::payload).filter(CallSitePayload.class::isInstance).map(CallSitePayload.class::cast).toList();
        List<Declaration> declarations = payloads(entities, Declaration.class); List<Operation> operations = payloads(entities, Operation.class);
        Set<String> liftedSymbols = new HashSet<>(); declarations.forEach(value -> liftedSymbols.addAll(value.sourceSymbolIds()));
        Set<String> mappedPsp = new HashSet<>(), mappedUir = new HashSet<>();
        for (SourceMap map : payloads(entities, SourceMap.class)) { mappedPsp.addAll(map.pspEntityIds()); mappedUir.addAll(map.uirEntityIds()); }
        long liftedCalls = sourceCalls.stream().filter(call -> mappedPsp.contains(call.callSiteId())).count();
        Set<String> sourceTypeIds = new HashSet<>(); sourceTypeEntities.forEach(value -> sourceTypeIds.add(value.entityId()));
        Set<String> resolvedSourceTypes = new HashSet<>();
        entities.stream().filter(value -> value.payload() instanceof UirModels.Type type && !Set.of("unknown", "unresolved", "error", "dynamic").contains(type.kind()))
                .filter(value -> value.provenance() != null && value.provenance().pass().equals("type-lift"))
                .forEach(value -> value.provenance().inputEntityIds().stream().filter(sourceTypeIds::contains).forEach(resolvedSourceTypes::add));
        List<Declaration> callables = declarations.stream().filter(value -> CALLABLE_KINDS.contains(value.kind()))
                .filter(value -> value.modifiers().stream().noneMatch(BODYLESS_MODIFIERS::contains)).toList();
        Set<String> regions = payloads(entities, Region.class).stream().map(Region::regionId).collect(java.util.stream.Collectors.toSet());
        long bodies = callables.stream().filter(value -> value.bodyRegionId() != null && regions.contains(value.bodyRegionId())).count();
        List<Operation> executable = operations.stream().filter(value -> !TERMINATORS.contains(value.opcode())).toList();
        Map<String,Effect> effects = new HashMap<>(); payloads(entities, Effect.class).forEach(value -> effects.put(value.effectId(), value));
        long effected = executable.stream().filter(value -> !value.effectIds().isEmpty() && value.effectIds().stream().allMatch(effects::containsKey)).count();
        long unknown = executable.stream().filter(value -> value.opcode().equals("unknown") || "unresolved".equals(value.attributes().get("resolution"))).count();
        long opaque = executable.stream().filter(value -> value.opcode().equals("opaque") || value.dialect().startsWith("uir.lang.")).count();
        long unresolved = executable.stream().filter(value -> "unresolved".equals(value.attributes().get("resolution"))).count();
        long dynamic = executable.stream().filter(value -> value.dialect().equals("uir.dynamic") || value.opcode().equals("opaque")).count();
        long mappable = declarations.size() + executable.size();
        long mapped = java.util.stream.Stream.concat(declarations.stream().map(Declaration::declarationId), executable.stream().map(Operation::operationId)).filter(mappedUir::contains).distinct().count();
        return new Coverage(rate(liftedSymbols.size(), sourceSymbols.size(), 1), rate(liftedCalls, sourceCalls.size(), 1), rate(mapped, mappable, 1),
                rate(resolvedSourceTypes.size(), sourceTypeEntities.size(), 1), rate(bodies, callables.size(), 1), rate(effected, executable.size(), 1), rate(unknown, executable.size(), 0),
                rate(opaque, executable.size(), 0), rate(unresolved, executable.size(), 0), rate(dynamic, executable.size(), 0));
    }

    private ModuleGate gate(String moduleId, List<Entity> entities, Coverage coverage, List<String> violations) {
        List<String> restrictions = new ArrayList<>(); boolean blocking = payloads(entities, Diagnostic.class).stream().anyMatch(Diagnostic::blocking);
        boolean integrity = violations.stream().noneMatch(value -> entities.stream().anyMatch(entity -> value.contains(entity.entityId())))
                && violations.stream().noneMatch(value -> value.equals("MANIFEST_COVERAGE_STALE") || value.startsWith("MANIFEST_PSP_"));
        List<Obligation> openBlocking = payloads(entities, Obligation.class).stream().filter(value -> value.severity().equals("blocking") && !Set.of("verified", "waived").contains(value.status())).toList();
        long unstrategized = openBlocking.stream().filter(value -> value.verificationStrategy().isEmpty()).count();
        boolean gateA = integrity && coverage.declarationLiftRate() >= .99 && coverage.operationLiftRate() >= .97 && coverage.sourceMapCoverage() >= .99;
        boolean gateB = gateA && coverage.typeCoverage() >= .90 && coverage.callableBodyCoverage() >= .90 && !blocking;
        boolean gateC = gateB && coverage.typeCoverage() >= .95 && coverage.effectCoverage() >= .90 && coverage.unknownOperationRate() <= .05 && coverage.opaqueOperationRate() <= .03 && unstrategized == 0;
        boolean gateD = gateC && coverage.typeCoverage() >= .98 && coverage.effectCoverage() >= .97 && coverage.unresolvedCallRate() <= .03 && coverage.dynamicHighRiskRate() <= .01 && coverage.sourceMapCoverage() >= .995;
        if (!integrity) restrictions.add("integrity-failure"); if (blocking) restrictions.add("blocking-diagnostic");
        if (coverage.opaqueOperationRate() > 0) restrictions.add("opaque-operation-strategy-required");
        if (coverage.dynamicHighRiskRate() > .01) restrictions.add("dynamic-runtime-evidence-required");
        if (!openBlocking.isEmpty()) restrictions.add("open-blocking-obligation");
        if (unstrategized > 0) restrictions.add("blocking-obligation-without-strategy");
        return new ModuleGate(moduleId, gateD ? "UIR-D" : gateC ? "UIR-C" : gateB ? "UIR-B" : gateA ? "UIR-A" : "NONE", gateB, gateC, restrictions, coverage);
    }

    private void validateEntity(Entity entity, Map<String,Entity> byId, Set<String> pspIds, Map<String,Long> fileBytes,
                                Set<String> blockArguments, List<String> violations) {
        if (entity.provenance() != null) {
            for (String input : entity.provenance().inputEntityIds()) if (!byId.containsKey(input) && !pspIds.contains(input)) violations.add("PROVENANCE_INPUT_MISSING:" + entity.entityId() + ":" + input);
            for (String transformation : entity.provenance().transformationIds()) requiredKind(transformation, "transformation", byId, entity, "PROVENANCE_TRANSFORMATION", violations);
        }
        Object payload = entity.payload();
        if (payload instanceof UirModels.Module value) value.declarationIds().forEach(id -> requiredKind(id, "declaration", byId, entity, "MODULE_DECLARATION", violations));
        else if (payload instanceof Declaration value) {
            optionalKind(value.containerDeclarationId(), "declaration", byId, entity, "DECLARATION_CONTAINER", violations);
            requiredKind(value.typeId(), "type", byId, entity, "DECLARATION_TYPE", violations);
            optionalKind(value.bodyRegionId(), "region", byId, entity, "DECLARATION_BODY", violations);
        } else if (payload instanceof UirModels.Type value) {
            optionalKind(value.declarationId(), "declaration", byId, entity, "TYPE_DECLARATION", violations);
            value.typeArguments().forEach(id -> requiredKind(id, "type", byId, entity, "TYPE_ARGUMENT", violations));
            value.parameterTypeIds().forEach(id -> requiredKind(id, "type", byId, entity, "PARAMETER_TYPE", violations));
            optionalKind(value.returnTypeId(), "type", byId, entity, "RETURN_TYPE", violations);
            if (value.confidence() < 0 || value.confidence() > 1) violations.add("TYPE_CONFIDENCE_INVALID:" + entity.entityId());
        } else if (payload instanceof Operation value) {
            if (!dialects.supports(value.dialect(), value.opcode())) violations.add("OPERATION_NOT_IN_DIALECT:" + entity.entityId());
            value.operands().forEach(id -> requiredKind(id, "value", byId, entity, "OPERAND", violations));
            for (int index = 0; index < value.results().size(); index++) {
                Result result = value.results().get(index); requiredKind(result.typeId(), "type", byId, entity, "RESULT_TYPE", violations);
                requiredKind(result.valueId(), "value", byId, entity, "RESULT_VALUE", violations);
                Entity resultEntity = byId.get(result.valueId());
                if (resultEntity != null && resultEntity.payload() instanceof Value produced
                        && (produced.definition() == null || !produced.definition().operationId().equals(value.operationId()) || produced.definition().resultIndex() != index))
                    violations.add("RESULT_DEFINITION_MISMATCH:" + entity.entityId() + ":" + result.valueId());
            }
            value.regionIds().forEach(id -> requiredKind(id, "region", byId, entity, "OPERATION_REGION", violations));
            value.effectIds().forEach(id -> requiredKind(id, "effect", byId, entity, "OPERATION_EFFECT", violations));
            value.sourceMapIds().forEach(id -> requiredKind(id, "source-map", byId, entity, "OPERATION_SOURCE_MAP", violations));
            if (value.evaluation() == null || value.confidence() < 0 || value.confidence() > 1) violations.add("OPERATION_SEMANTICS_INVALID:" + entity.entityId());
        } else if (payload instanceof Region value) {
            value.blockIds().forEach(id -> requiredKind(id, "block", byId, entity, "REGION_BLOCK", violations));
            requiredKind(value.entryBlockId(), "block", byId, entity, "REGION_ENTRY", violations);
            if (!value.blockIds().contains(value.entryBlockId())) violations.add("REGION_ENTRY_NOT_MEMBER:" + entity.entityId());
            validatePeer(entity, value.structuredPeerRegionId(), byId, violations); validatePeer(entity, value.cfgPeerRegionId(), byId, violations);
        } else if (payload instanceof Block value) {
            value.argumentValueIds().forEach(id -> requiredKind(id, "value", byId, entity, "BLOCK_ARGUMENT", violations));
            value.operationIds().forEach(id -> requiredKind(id, "operation", byId, entity, "BLOCK_OPERATION", violations));
            requiredKind(value.terminatorOperationId(), "operation", byId, entity, "BLOCK_TERMINATOR", violations);
            if (value.operationIds().isEmpty() || !value.operationIds().getLast().equals(value.terminatorOperationId())) violations.add("TERMINATOR_NOT_LAST_IN_BLOCK:" + entity.entityId());
            Entity terminator = byId.get(value.terminatorOperationId());
            if (terminator != null && terminator.payload() instanceof Operation operation && !TERMINATORS.contains(operation.opcode())) violations.add("BLOCK_TERMINATOR_OPCODE_INVALID:" + entity.entityId());
        } else if (payload instanceof Value value) {
            requiredKind(value.typeId(), "type", byId, entity, "VALUE_TYPE", violations);
            if (value.definition() == null && !blockArguments.contains(value.valueId())) violations.add("VALUE_DEFINITION_MISSING:" + entity.entityId());
            else {
                if (value.definition() != null) {
                    requiredKind(value.definition().operationId(), "operation", byId, entity, "VALUE_DEFINITION", violations);
                    Entity definition = byId.get(value.definition().operationId());
                    if (definition != null && definition.payload() instanceof Operation operation
                            && (value.definition().resultIndex() < 0 || value.definition().resultIndex() >= operation.results().size()
                            || !operation.results().get(value.definition().resultIndex()).valueId().equals(value.valueId())))
                        violations.add("VALUE_DEFINITION_RESULT_MISMATCH:" + entity.entityId());
                }
            }
            for (Use use : value.uses()) {
                requiredKind(use.operationId(), "operation", byId, entity, "VALUE_USE", violations);
                Entity using = byId.get(use.operationId());
                if (using != null && using.payload() instanceof Operation operation
                        && (use.operandIndex() < 0 || use.operandIndex() >= operation.operands().size() || !operation.operands().get(use.operandIndex()).equals(value.valueId())))
                    violations.add("VALUE_USE_OPERAND_MISMATCH:" + entity.entityId());
            }
            value.flowTypeIds().forEach(id -> requiredKind(id, "type", byId, entity, "FLOW_TYPE", violations));
        } else if (payload instanceof CfgEdge value) {
            requiredKind(value.fromBlockId(), "block", byId, entity, "CFG_FROM", violations); requiredKind(value.toBlockId(), "block", byId, entity, "CFG_TO", violations);
            value.argumentValueIds().forEach(id -> requiredKind(id, "value", byId, entity, "CFG_ARGUMENT", violations));
            Entity target = byId.get(value.toBlockId()); if (target != null && target.payload() instanceof Block block && block.argumentValueIds().size() != value.argumentValueIds().size()) violations.add("CFG_ARGUMENT_ARITY_MISMATCH:" + entity.entityId());
            for (TypeRefinement refinement : value.typeRefinements()) { requiredKind(refinement.valueId(), "value", byId, entity, "REFINEMENT_VALUE", violations); requiredKind(refinement.narrowedTypeId(), "type", byId, entity, "REFINEMENT_TYPE", violations); }
        } else if (payload instanceof Effect value) requiredKind(value.operationId(), "operation", byId, entity, "EFFECT_OPERATION", violations);
        else if (payload instanceof EffectSummary value) {
            requiredKind(value.callableDeclarationId(), "declaration", byId, entity, "EFFECT_SUMMARY_CALLABLE", violations);
            value.effectIds().forEach(id -> requiredKind(id, "effect", byId, entity, "EFFECT_SUMMARY_EFFECT", violations));
            if (value.confidence() < 0 || value.confidence() > 1) violations.add("EFFECT_SUMMARY_CONFIDENCE_INVALID:" + entity.entityId());
        }
        else if (payload instanceof ExceptionContract value) {
            requiredKind(value.callableDeclarationId(), "declaration", byId, entity, "EXCEPTION_CALLABLE", violations);
            value.declaredThrowTypeIds().forEach(id -> requiredKind(id, "type", byId, entity, "DECLARED_THROW_TYPE", violations));
            value.inferredThrowTypeIds().forEach(id -> requiredKind(id, "type", byId, entity, "INFERRED_THROW_TYPE", violations));
            value.promiseRejectionTypeIds().forEach(id -> requiredKind(id, "type", byId, entity, "REJECTION_TYPE", violations));
        } else if (payload instanceof AsyncContract value) {
            requiredKind(value.callableDeclarationId(), "declaration", byId, entity, "ASYNC_CALLABLE", violations); requiredKind(value.resultTypeId(), "type", byId, entity, "ASYNC_RESULT", violations);
        } else if (payload instanceof Alias value) requiredKind(value.valueId(), "value", byId, entity, "ALIAS_VALUE", violations);
        else if (payload instanceof Obligation value) {
            optionalKind(value.declarationId(), "declaration", byId, entity, "OBLIGATION_DECLARATION", violations); optionalKind(value.operationId(), "operation", byId, entity, "OBLIGATION_OPERATION", violations);
        } else if (payload instanceof SourceMap value) {
            value.uirEntityIds().forEach(id -> required(id, byId, entity, "SOURCE_MAP_UIR", violations));
            for (String id : value.pspEntityIds()) if (!pspIds.contains(id)) violations.add("SOURCE_MAP_PSP_MISSING:" + entity.entityId() + ":" + id);
            validateRange(entity, value.sourceRange(), fileBytes, violations);
        } else if (payload instanceof Transformation value) {
            if (value.inputEntityIds().isEmpty() || value.outputEntityIds().isEmpty()) violations.add("TRANSFORMATION_ENDPOINTS_EMPTY:" + entity.entityId());
            for (String id : value.inputEntityIds()) if (!byId.containsKey(id) && !pspIds.contains(id)) violations.add("TRANSFORMATION_INPUT_MISSING:" + entity.entityId() + ":" + id);
            value.outputEntityIds().forEach(id -> required(id, byId, entity, "TRANSFORMATION_OUTPUT", violations));
        }
    }

    private static void validatePeer(Entity entity, String peerId, Map<String,Entity> byId, List<String> violations) {
        if (peerId == null) return; requiredKind(peerId, "region", byId, entity, "REGION_PEER", violations); Entity peer = byId.get(peerId);
        if (peer != null && peer.payload() instanceof Region region && !entity.entityId().equals(region.structuredPeerRegionId()) && !entity.entityId().equals(region.cfgPeerRegionId())) violations.add("REGION_PEER_NOT_RECIPROCAL:" + entity.entityId());
    }
    private static void validateDominance(List<Entity> entities, Map<String,Entity> byId, List<String> violations) {
        List<CfgEdge> allEdges = payloads(entities, CfgEdge.class);
        for (Region region : payloads(entities, Region.class).stream().filter(value -> value.kind().equals("cfg")).toList()) {
            Set<String> blocks = new LinkedHashSet<>(region.blockIds()); if (blocks.isEmpty() || !blocks.contains(region.entryBlockId())) continue;
            Map<String,Set<String>> predecessors = new HashMap<>(); blocks.forEach(block -> predecessors.put(block, new LinkedHashSet<>()));
            for (CfgEdge edge : allEdges) if (blocks.contains(edge.fromBlockId()) && blocks.contains(edge.toBlockId())) predecessors.get(edge.toBlockId()).add(edge.fromBlockId());
            Map<String,Set<String>> dominators = new HashMap<>();
            for (String block : blocks) dominators.put(block, block.equals(region.entryBlockId()) ? new LinkedHashSet<>(Set.of(block)) : new LinkedHashSet<>(blocks));
            boolean changed;
            do {
                changed = false;
                for (String block : blocks) {
                    if (block.equals(region.entryBlockId())) continue; Set<String> next = new LinkedHashSet<>(); Set<String> preds = predecessors.get(block);
                    if (!preds.isEmpty()) { next.addAll(dominators.get(preds.iterator().next())); for (String predecessor : preds) next.retainAll(dominators.get(predecessor)); }
                    next.add(block); if (!next.equals(dominators.get(block))) { dominators.put(block, next); changed = true; }
                }
            } while (changed);
            Map<String,Set<String>> operationBlocks = new HashMap<>();
            for (String blockId : blocks) {
                Entity blockEntity = byId.get(blockId); if (blockEntity == null || !(blockEntity.payload() instanceof Block block)) continue;
                for (String operation : block.operationIds()) operationBlocks.computeIfAbsent(operation, ignored -> new LinkedHashSet<>()).add(blockId);
            }
            for (String blockId : blocks) {
                Entity blockEntity = byId.get(blockId); if (blockEntity == null || !(blockEntity.payload() instanceof Block block)) continue;
                Map<String,Integer> position = new HashMap<>(); for (int index = 0; index < block.operationIds().size(); index++) position.put(block.operationIds().get(index), index);
                for (int useIndex = 0; useIndex < block.operationIds().size(); useIndex++) {
                    Entity operationEntity = byId.get(block.operationIds().get(useIndex)); if (operationEntity == null || !(operationEntity.payload() instanceof Operation operation)) continue;
                    for (String operand : operation.operands()) {
                        if (block.argumentValueIds().contains(operand)) continue; Entity valueEntity = byId.get(operand); if (valueEntity == null || !(valueEntity.payload() instanceof Value value) || value.definition() == null) continue;
                        String definitionOperation = value.definition().operationId(); Set<String> definitionBlocks = operationBlocks.getOrDefault(definitionOperation, Set.of());
                        if (definitionBlocks.contains(blockId) && position.getOrDefault(definitionOperation, Integer.MAX_VALUE) >= useIndex) violations.add("SSA_USE_BEFORE_DEFINITION:" + operation.operationId() + ":" + operand);
                        else if (!definitionBlocks.isEmpty() && definitionBlocks.stream().noneMatch(dominators.get(blockId)::contains)) violations.add("SSA_DEFINITION_DOES_NOT_DOMINATE_USE:" + operation.operationId() + ":" + operand);
                    }
                }
            }
        }
    }
    private static void validateRange(Entity entity, SourceRange range, Map<String,Long> fileBytes, List<String> violations) {
        if (range == null) return; Long bytes = fileBytes.get(range.fileId());
        if (bytes == null) violations.add("SOURCE_MAP_FILE_MISSING:" + entity.entityId() + ":" + range.fileId());
        else if (range.startByte() < 0 || range.endByte() < range.startByte() || range.endByte() > bytes) violations.add("SOURCE_MAP_RANGE_INVALID:" + entity.entityId());
    }
    private static SemanticDataset subset(SemanticDataset psp, String project) { return new SemanticDataset(psp.manifest(), psp.entities().stream().filter(entity -> entity.projectId().equals(project)).toList()); }
    private static void required(String id, Map<String,Entity> byId, Entity entity, String kind, List<String> violations) { if (id == null || !byId.containsKey(id)) violations.add(kind + "_MISSING:" + (entity == null ? "manifest" : entity.entityId()) + ":" + id); }
    private static void requiredKind(String id, String expectedKind, Map<String,Entity> byId, Entity entity, String relation, List<String> violations) {
        required(id, byId, entity, relation, violations); Entity target = byId.get(id);
        if (target != null && !target.entityKind().equals(expectedKind)) violations.add(relation + "_KIND_INVALID:" + (entity == null ? "manifest" : entity.entityId()) + ":" + id);
    }
    private static void optionalKind(String id, String expectedKind, Map<String,Entity> byId, Entity entity, String relation, List<String> violations) { if (id != null) requiredKind(id, expectedKind, byId, entity, relation, violations); }
    private static double rate(long numerator, long denominator, double empty) { return denominator == 0 ? empty : Math.round(Math.min(numerator, denominator) * 100_000d / denominator) / 100_000d; }
    private static <T> List<T> payloads(List<Entity> entities, Class<T> type) { return entities.stream().map(Entity::payload).filter(type::isInstance).map(type::cast).toList(); }
}
