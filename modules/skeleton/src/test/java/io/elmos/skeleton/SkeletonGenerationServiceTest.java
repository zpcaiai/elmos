package io.elmos.skeleton;

import io.elmos.uir.UirModels;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;

import static io.elmos.skeleton.SkeletonModels.*;
import static org.junit.jupiter.api.Assertions.*;

class SkeletonGenerationServiceTest {
    @TempDir Path root;
    private final Clock clock=Clock.fixed(Instant.parse("2026-07-21T01:00:00Z"), ZoneOffset.UTC);

    @Test void generatesDeterministicTraceablePendingSkeletonAndGatesOnRecordedBaseline() throws Exception {
        BuildBaseline passed=new BuildBaseline(Status.PASSED,Status.PASSED,Status.PASSED,Status.PASSED,"sandbox:image@sha256:"+"d".repeat(64),List.of(),List.of("artifact:build","artifact:discovery"));
        SkeletonGenerationService service=new SkeletonGenerationService(clock,(repository,plan)->passed);
        Result first=service.generate(root.resolve("migration"),uir(),uirReport(),profile()), second=service.generate(root.resolve("migration"),uir(),uirReport(),profile());
        assertEquals(first.plan().generationId(),second.plan().generationId()); assertEquals(first.manifest().createdFiles(),second.manifest().createdFiles());
        assertTrue(first.conformance().eligibleForBatch5()); assertEquals("passed",first.conformance().status()); assertEquals(1,first.manifest().placeholderCount());
        assertTrue(Files.isRegularFile(root.resolve("migration/target-repository/MigrationSkeleton.csproj")));
        Path pending=first.manifest().createdFiles().stream().filter(GeneratedFile::provisional).filter(file->file.kind().equals("source")).map(file->root.resolve("migration/target-repository").resolve(file.path())).findFirst().orElseThrow();
        String content=Files.readString(pending); assertTrue(content.contains("MIGRATION_BODY_PENDING")); assertFalse(content.contains("return null"));
        assertTrue(Files.isRegularFile(root.resolve("migration/target-plan/target-skeleton-manifest.json")));
        assertTrue(first.plan().mappings().stream().allMatch(mapping->!mapping.uirEntities().isEmpty()&&!mapping.targetEntities().isEmpty()));
    }

    @Test void notRunBaselineBlocksAndManualConflictIsNeverOverwritten() throws Exception {
        SkeletonGenerationService service=new SkeletonGenerationService(clock,(repository,plan)->BuildBaseline.notRun("approved runner missing"));
        Result result=service.generate(root.resolve("blocked"),uir(),uirReport(),profile()); assertFalse(result.conformance().eligibleForBatch5()); assertEquals("blocked",result.conformance().status());
        Path generated=root.resolve("blocked/target-repository/README.md"); Files.writeString(generated,"manual change");
        assertThrows(IllegalStateException.class,()->service.generate(root.resolve("blocked"),uir(),uirReport(),profile()));
        TargetProfile unresolved=new TargetProfile("profile:bad","csharp","exact","net8.0",null,"msbuild",List.of("container"),"library",List.of(),List.of(),Map.of(),true,List.of(),List.of(),List.of("test framework approval"));
        assertThrows(IllegalStateException.class,()->service.generate(root.resolve("bad"),uir(),uirReport(),unresolved));
    }

    private UirModels.Dataset uir(){String snapshot="snap",sem="sem",run="uir",module="module:orders",type="uirtype:order",clazz="uirdecl:order",method="uirdecl:find",provId="prov";UirModels.Provenance prov=new UirModels.Provenance(provId,"fixture","1",List.of(),List.of(),"fixture",Instant.EPOCH);List<UirModels.Entity>entities=List.of(
            new UirModels.Entity("type",type,snapshot,sem,run,module,new UirModels.Type(type,"nominal","Order",clazz,List.of(),new UirModels.Nullability("non-null","source"),null,null,List.of(),null,List.of(),List.of(),"declared",1,Map.of()),prov),
            new UirModels.Entity("declaration",clazz,snapshot,sem,run,module,new UirModels.Declaration(clazz,"class","Order","source.Order",null,"public",List.of(),type,List.of(),List.of(),null,List.of("sym:order"),Map.of()),prov),
            new UirModels.Entity("declaration",method,snapshot,sem,run,module,new UirModels.Declaration(method,"method","findOrder","source.Order.findOrder",clazz,"public",List.of("async"),type,List.of(),List.of(),"region:body",List.of("sym:find"),Map.of()),prov),
            new UirModels.Entity("module",module,snapshot,sem,run,module,new UirModels.Module(module,"source-project:orders","java",List.of(clazz,method),List.of("uir.core"),Map.of()),prov));
        UirModels.Coverage coverage=new UirModels.Coverage(1,1,1,1,1,1,0,0,0,0);return new UirModels.Dataset(new UirModels.RunManifest(run,sem,snapshot,"completed","1.0",List.of(module),List.of("uir.core"),List.of(),"hash",coverage,List.of(),Instant.EPOCH),entities);}
    private UirModels.ConformanceReport uirReport(){UirModels.Coverage c=new UirModels.Coverage(1,1,1,1,1,1,0,0,0,0);return new UirModels.ConformanceReport(3,"passed",List.of(new UirModels.ModuleGate("module:orders","UIR-D",true,true,List.of(),c)),c,List.of(),List.of(),List.of(),List.of());}
    private TargetProfile profile(){return new TargetProfile("target-profile:csharp","csharp","exact","net8.0",null,"msbuild",List.of("container"),"library",List.of(),List.of(),Map.of("typeCase","pascal"),true,List.of("no-preview"),List.of(),List.of());}
}
