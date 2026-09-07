package io.elmos.uir;

import com.github.luben.zstd.ZstdInputStream;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.semantic.PspModels.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static io.elmos.uir.UirModels.*;
import static org.junit.jupiter.api.Assertions.*;

class PspToUirPipelineTest {
    @TempDir Path root;
    private final Clock clock = Clock.fixed(Instant.parse("2026-07-21T00:00:00Z"), ZoneOffset.UTC);

    @Test void liftsEligiblePspToTraceableUirButKeepsIncompleteBodyFailClosed() throws Exception {
        SemanticDataset psp = psp(); io.elmos.semantic.PspModels.ConformanceReport pspReport = pspReport(true);
        UirDialectRegistry dialects = new UirDialectRegistry(); PspToUirLifter lifter = new PspToUirLifter(dialects, clock);
        Dataset first = lifter.lift(psp, pspReport, LiftProfile.full()), second = lifter.lift(psp, pspReport, LiftProfile.full());
        assertEquals(first.manifest().uirRunId(), second.manifest().uirRunId());
        assertEquals(first.entities().stream().map(Entity::entityId).toList(), second.entities().stream().map(Entity::entityId).toList());
        assertEquals("completed_with_restrictions", first.manifest().status());
        assertTrue(first.entities().stream().allMatch(entity -> entity.contentHash().startsWith("sha256:") && entity.generation() == 1 && !entity.deleted()));
        assertEquals(2, first.entities().stream().filter(entity -> entity.payload() instanceof Region).count());
        assertTrue(first.entities().stream().anyMatch(entity -> entity.payload() instanceof Region region && region.kind().equals("structured") && region.cfgPeerRegionId() != null));
        assertTrue(first.entities().stream().anyMatch(entity -> entity.payload() instanceof CfgEdge edge && edge.kind().equals("true")));
        assertTrue(first.entities().stream().anyMatch(entity -> entity.payload() instanceof Effect effect && effect.kind().equals("unknown")), "unknown external calls are explicit effects");
        assertTrue(first.entities().stream().anyMatch(entity -> entity.payload() instanceof EffectSummary summary && summary.effectIds().size() == 2 && summary.mayThrow()));
        assertTrue(first.entities().stream().anyMatch(entity -> entity.payload() instanceof SourceMap map && map.mappingKind().equals("normalized")));
        assertTrue(first.entities().stream().anyMatch(entity -> entity.payload() instanceof Operation operation && operation.opcode().equals("opaque")
                && operation.attributes().get("reason").equals("psp-call-sites-do-not-cover-complete-body")));
        assertTrue(first.entities().stream().anyMatch(entity -> entity.payload() instanceof Obligation obligation && obligation.severity().equals("blocking")
                && obligation.verificationStrategy().contains("differential-test")));

        UirModels.ConformanceReport report = new UirConformanceValidator(dialects).validate(first, psp);
        assertEquals("passed_with_restrictions", report.status(), report.toString()); assertEquals("UIR-B", report.modules().getFirst().gate());
        assertTrue(report.modules().getFirst().eligibleForSkeletonGeneration()); assertFalse(report.modules().getFirst().eligibleForAutomaticTranslation());
        assertTrue(report.modules().getFirst().restrictions().contains("opaque-operation-strategy-required"));

        Path workspace = root.resolve("workspace"); new UirArtifactWriter().write(workspace, first, report, dialects);
        for (String artifact : List.of("uir-run-manifest.json","protocol-version.json","dialect-registry.json","modules.jsonl.zst","declarations.jsonl.zst","types.jsonl.zst","operations.jsonl.zst","regions.jsonl.zst","blocks.jsonl.zst","values.jsonl.zst","cfg-edges.jsonl.zst","effects.jsonl.zst","source-maps.jsonl.zst","indexes/uir-index.sqlite"))
            assertTrue(Files.isRegularFile(workspace.resolve("uir").resolve(artifact)), artifact);
        try (var input = new ZstdInputStream(Files.newInputStream(workspace.resolve("uir/operations.jsonl.zst")));
             var lines = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8)).lines()) { assertEquals(5, lines.count()); }
        try (var connection = DriverManager.getConnection("jdbc:sqlite:" + workspace.resolve("uir/indexes/uir-index.sqlite").toAbsolutePath());
             var result = connection.createStatement().executeQuery("select count(*), min(generation), min(length(content_hash)) from entities")) {
            assertTrue(result.next()); assertEquals(first.entities().size(), result.getInt(1)); assertEquals(1, result.getInt(2)); assertTrue(result.getInt(3) > 10);
        }
        try (var connection = DriverManager.getConnection("jdbc:sqlite:" + workspace.resolve("uir/indexes/uir-index.sqlite").toAbsolutePath());
             var result = connection.createStatement().executeQuery("select count(*) from links where link_kind in ('MAPS_FROM_PSP','MAPS_TO_UIR','HAS_EFFECT')")) {
            assertTrue(result.next()); assertTrue(result.getInt(1) >= 3);
        }
    }

    @Test void blocksIneligiblePspAndFindsDanglingUirOperands() {
        SemanticDataset psp = psp(); UirDialectRegistry dialects = new UirDialectRegistry();
        Dataset blocked = new PspToUirLifter(dialects, clock).lift(psp, pspReport(false), LiftProfile.full());
        assertTrue(blocked.entities().stream().noneMatch(entity -> entity.payload() instanceof UirModels.Module));
        assertTrue(blocked.entities().stream().anyMatch(entity -> entity.payload() instanceof Diagnostic diagnostic && diagnostic.blocking()));
        UirModels.ConformanceReport blockedReport = new UirConformanceValidator(dialects).validate(blocked, psp);
        assertEquals("blocked", blockedReport.status()); assertEquals(1, blockedReport.modules().size()); assertEquals("NONE", blockedReport.modules().getFirst().gate());

        Dataset valid = new PspToUirLifter(dialects, clock).lift(psp, pspReport(true), LiftProfile.full()); List<Entity> changed = new ArrayList<>(valid.entities());
        Entity call = changed.stream().filter(entity -> entity.payload() instanceof Operation operation && operation.opcode().equals("call")).findFirst().orElseThrow(); Operation operation = (Operation) call.payload();
        changed.set(changed.indexOf(call), new Entity(call.entityKind(), call.entityId(), call.snapshotId(), call.semanticRunId(), call.uirRunId(), call.moduleId(),
                new Operation(operation.operationId(), operation.dialect(), operation.opcode(), List.of("value:missing"), operation.results(), operation.attributes(), operation.regionIds(), operation.effectIds(), operation.sourceMapIds(), operation.evaluation(), operation.confidence()), call.provenance()));
        UirModels.ConformanceReport report = new UirConformanceValidator(dialects).validate(new Dataset(valid.manifest(), changed), psp);
        assertEquals("failed", report.status()); assertTrue(report.violations().stream().anyMatch(value -> value.startsWith("OPERAND_MISSING")));
    }

    @Test void rejectsDanglingOperationResultsAndSymlinkedArtifactDirectories() throws Exception {
        SemanticDataset psp = psp(); UirDialectRegistry dialects = new UirDialectRegistry();
        Dataset valid = new PspToUirLifter(dialects, clock).lift(psp, pspReport(true), LiftProfile.full());
        List<Entity> changed = new ArrayList<>(valid.entities());
        Entity call = changed.stream().filter(entity -> entity.payload() instanceof Operation operation && operation.opcode().equals("call")).findFirst().orElseThrow();
        Operation operation = (Operation) call.payload();
        changed.set(changed.indexOf(call), new Entity(call.entityKind(), call.entityId(), call.snapshotId(), call.semanticRunId(), call.uirRunId(), call.moduleId(),
                new Operation(operation.operationId(), operation.dialect(), operation.opcode(), operation.operands(), List.of(new Result("value:missing", operation.results().getFirst().typeId())), operation.attributes(), operation.regionIds(), operation.effectIds(), operation.sourceMapIds(), operation.evaluation(), operation.confidence()), call.provenance()));
        UirModels.ConformanceReport invalid = new UirConformanceValidator(dialects).validate(new Dataset(valid.manifest(), changed), psp);
        assertEquals("failed", invalid.status()); assertTrue(invalid.violations().stream().anyMatch(value -> value.startsWith("RESULT_VALUE_MISSING")));

        UirModels.ConformanceReport report = new UirConformanceValidator(dialects).validate(valid, psp);
        Path workspace = root.resolve("symlink-workspace"), outside = root.resolve("outside"); Files.createDirectories(workspace); Files.createDirectories(outside);
        Files.createSymbolicLink(workspace.resolve("uir"), outside);
        SecurityException error = assertThrows(SecurityException.class, () -> new UirArtifactWriter().write(workspace, valid, report, dialects));
        assertTrue(error.getMessage().startsWith("UIR_OUTPUT_SYMLINK")); try (var files = Files.list(outside)) { assertEquals(0, files.count()); }

        Path nestedWorkspace = root.resolve("nested-symlink-workspace"); Files.createDirectories(nestedWorkspace.resolve("uir"));
        Files.createSymbolicLink(nestedWorkspace.resolve("uir/indexes"), outside);
        SecurityException nested = assertThrows(SecurityException.class, () -> new UirArtifactWriter().write(nestedWorkspace, valid, report, dialects));
        assertTrue(nested.getMessage().startsWith("UIR_OUTPUT_SYMLINK")); try (var files = Files.list(outside)) { assertEquals(0, files.count()); }
    }

    @Test void contentHashIsCanonicalAcrossMapInsertionOrder() {
        Map<String,Object> first = new LinkedHashMap<>(), second = new LinkedHashMap<>();
        first.put("b", List.of(2, 1)); first.put("a", "value"); second.put("a", "value"); second.put("b", List.of(2, 1));
        assertEquals(UirIds.contentHash(first), UirIds.contentHash(second));
    }

    @Test void readsPreIncrementalV1EntityWithSafeDefaults() throws Exception {
        String legacy = """
                {"entityKind":"diagnostic","entityId":"diag:legacy","snapshotId":"snap","semanticRunId":"sem","uirRunId":"uir","moduleId":"module",
                 "payload":{"message":"legacy"},"provenance":{"provenanceId":"prov","pass":"legacy","passVersion":"1.0","inputEntityIds":[],"transformationIds":[],"confidenceReason":"legacy artifact","observedAt":"1970-01-01T00:00:00Z"}}
                """;
        Entity entity = new ObjectMapper().findAndRegisterModules().readValue(legacy, Entity.class);
        assertEquals(1, entity.generation()); assertTrue(entity.contentHash().startsWith("sha256:")); assertFalse(entity.deleted()); assertNull(entity.supersedes());
    }

    @Test void detectsLocalSsaUseBeforeDefinitionInDerivedCfg() {
        SemanticDataset psp = psp(); UirDialectRegistry dialects = new UirDialectRegistry();
        Dataset valid = new PspToUirLifter(dialects, clock).lift(psp, pspReport(true), LiftProfile.full()); List<Entity> changed = new ArrayList<>(valid.entities());
        Entity callEntity = changed.stream().filter(entity -> entity.payload() instanceof Operation operation && operation.opcode().equals("call")).findFirst().orElseThrow();
        Operation call = (Operation) callEntity.payload(); String valueId = call.results().getFirst().valueId();
        Entity opaqueEntity = changed.stream().filter(entity -> entity.payload() instanceof Operation operation && operation.opcode().equals("opaque")).findFirst().orElseThrow();
        Operation opaque = (Operation) opaqueEntity.payload();
        changed.set(changed.indexOf(opaqueEntity), new Entity(opaqueEntity.entityKind(), opaqueEntity.entityId(), opaqueEntity.snapshotId(), opaqueEntity.semanticRunId(), opaqueEntity.uirRunId(), opaqueEntity.moduleId(),
                new Operation(opaque.operationId(), opaque.dialect(), opaque.opcode(), List.of(valueId), opaque.results(), opaque.attributes(), opaque.regionIds(), opaque.effectIds(), opaque.sourceMapIds(), opaque.evaluation(), opaque.confidence()), opaqueEntity.provenance()));
        Region cfg = changed.stream().map(Entity::payload).filter(Region.class::isInstance).map(Region.class::cast).filter(region -> region.kind().equals("cfg")).findFirst().orElseThrow();
        Entity blockEntity = changed.stream().filter(entity -> entity.entityId().equals(cfg.entryBlockId())).findFirst().orElseThrow(); Block block = (Block) blockEntity.payload();
        changed.set(changed.indexOf(blockEntity), new Entity(blockEntity.entityKind(), blockEntity.entityId(), blockEntity.snapshotId(), blockEntity.semanticRunId(), blockEntity.uirRunId(), blockEntity.moduleId(),
                new Block(block.blockId(), block.argumentValueIds(), List.of(opaque.operationId(), call.operationId(), block.terminatorOperationId()), block.terminatorOperationId(), block.reachable()), blockEntity.provenance()));
        UirModels.ConformanceReport report = new UirConformanceValidator(dialects).validate(new Dataset(valid.manifest(), changed), psp);
        assertEquals("failed", report.status()); assertTrue(report.violations().stream().anyMatch(value -> value.startsWith("SSA_USE_BEFORE_DEFINITION")));
    }

    private SemanticDataset psp() {
        String snapshot = "snapshot:fixture", run = "semrun:fixture", project = "project:fixture", file = "file:fixture", type = "type:int", scope = "scope:file", node = "node:callable", symbol = "sym:caller", call = "call:site";
        SourceRange whole = new SourceRange(file, 0, 20, 1, 0, 1, 20), callRange = new SourceRange(file, 2, 8, 1, 2, 1, 8);
        io.elmos.semantic.PspModels.Provenance provenance = new io.elmos.semantic.PspModels.Provenance("fixture-adapter","1","javac","21","fixture","full","compiler-selected",1,List.of("sha256:x"),Instant.EPOCH);
        List<EntityEnvelope> entities = List.of(
                envelope("file",file,new FilePayload(file,project,"A.java","java","sha256:x",20,"UTF-8","LF","production-source",false,false,"javac",false),snapshot,run,project,provenance),
                envelope("syntax-node",node,new SyntaxNodePayload(node,"method",null,whole,false,List.of(),List.of(),Map.of()),snapshot,run,project,provenance),
                envelope("scope",scope,new ScopePayload(scope,"file",null,null,whole),snapshot,run,project,provenance),
                envelope("type",type,new TypePayload(type,"primitive","int","java.lang.Integer",List.of(),List.of(),null,List.of(),"non-null","immutable","compiler",1,Map.of("bitWidth",32)),snapshot,run,project,provenance),
                envelope("symbol",symbol,new SymbolPayload(symbol,"method","run","A.run",null,scope,"public",List.of("static"),List.of(new DeclarationSite(file,node,whole)),type,Map.of(),List.of(),true,false,Map.of()),snapshot,run,project,provenance),
                envelope("call-site",call,new CallSitePayload(call,symbol,node,"sha256:call","static","compiler-selected",symbol,List.of(symbol),null,List.of(),type,"sync",1,callRange,Map.of()),snapshot,run,project,provenance),
                envelope("control-flow","cfg:caller",new ControlFlowPayload(symbol,"native-entry",List.of(
                        new ControlBlock("native-entry",new SourceRange(file,0,10,1,0,1,10),List.of("branch")),
                        new ControlBlock("native-exit",new SourceRange(file,10,20,1,10,1,20),List.of("return"))),
                        List.of(new ControlEdge("native-entry","native-exit","true")),List.of("return"),Map.of("mayThrow",false),"javac:cfg",List.of()),snapshot,run,project,provenance),
                envelope("source-map","smap:source",new SourceMapPayload(node,symbol,type,null,call,callRange,List.of()),snapshot,run,project,provenance));
        CoverageMetrics metrics = new CoverageMetrics(1,1,1,1,0,0,0,1); SemanticRunManifest manifest = new SemanticRunManifest(run,snapshot,"completed",List.of(),List.of(project),List.of(),metrics,List.of(),"sha256:config",Instant.EPOCH);
        return new SemanticDataset(manifest,entities);
    }
    private io.elmos.semantic.PspModels.ConformanceReport pspReport(boolean eligible) {
        CoverageMetrics metrics = new CoverageMetrics(1,1,1,1,0,0,0,1); io.elmos.semantic.PspModels.ModuleGate gate = new io.elmos.semantic.PspModels.ModuleGate("project:fixture", eligible ? "C" : "NONE", eligible, eligible, eligible ? List.of() : List.of("blocking-diagnostic"),metrics);
        return new io.elmos.semantic.PspModels.ConformanceReport(eligible ? "passed" : "blocked",2,List.of(gate),metrics,eligible ? List.of() : List.of("diag:block"),List.of(),List.of());
    }
    private EntityEnvelope envelope(String kind, String id, Object payload, String snapshot, String run, String project, io.elmos.semantic.PspModels.Provenance provenance) { return new EntityEnvelope(io.elmos.semantic.PspModels.PROTOCOL_VERSION,kind,id,snapshot,run,project,"java",payload,provenance); }
}
