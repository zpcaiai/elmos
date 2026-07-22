package io.elmos.lowering;

import io.elmos.skeleton.SkeletonGenerationService;
import io.elmos.skeleton.SkeletonModels;
import io.elmos.uir.UirModels;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.*;

import static io.elmos.lowering.LoweringModels.*;
import static org.junit.jupiter.api.Assertions.*;

class MethodBodyLoweringServiceTest {
    @TempDir Path root;
    private final Clock clock=Clock.fixed(Instant.parse("2026-07-21T02:00:00Z"), ZoneOffset.UTC);

    @Test void faithfulBodyIsValidatedPatchedTraceableAndIdempotent() throws Exception {
        Fixture fixture=fixture(root.resolve("faithful"),false);MethodBodyLoweringService service=service(true);
        RunResult first=service.lower(request(fixture,true,"balanced")),second=service.lower(request(fixture,true,"balanced"));
        assertTrue(first.conformance().eligibleForBatch6());assertEquals("L-D",first.conformance().modules().getFirst().gate());assertEquals("verified",first.results().getFirst().status());assertEquals("applied",first.results().getFirst().patch().status());assertEquals("unchanged",second.results().getFirst().patch().status());
        String target=Files.readString(fixture.workspace.resolve("target-repository").resolve(first.plans().getFirst().targetFile()));assertTrue(target.contains("return findOrder();"));assertFalse(target.contains("Order result = findOrder();"));assertFalse(target.contains("MIGRATION_BODY_PENDING"));assertTrue(Files.isRegularFile(fixture.workspace.resolve("reports/batch-5-conformance-report.json")));assertEquals(first.manifest().loweringRunId(),second.manifest().loweringRunId());
    }

    @Test void opaqueCallableIsNeverRenderedAsEmptySuccessAndGetsBoundedAgentPacket() throws Exception {
        Fixture fixture=fixture(root.resolve("opaque"),true);RunResult result=service(true).lower(request(fixture,true,"strict"));
        assertFalse(result.conformance().eligibleForBatch6());assertEquals("agent-required",result.results().getFirst().status());assertNotNull(result.results().getFirst().agentPacket());assertNull(result.results().getFirst().patch());assertTrue(result.results().getFirst().agentPacket().constraints().contains("patch-only"));
        String target=Files.readString(fixture.workspace.resolve("target-repository").resolve(result.plans().getFirst().targetFile()));assertTrue(target.contains("MIGRATION_BODY_PENDING"));
    }

    @Test void failedOrMissingStaticBackendBlocksPatchAndIdiomaticPhase() throws Exception {
        Fixture fixture=fixture(root.resolve("blocked"),false);RunResult failed=service(false).lower(request(fixture,true,"idiomatic"));
        assertEquals("blocked",failed.results().getFirst().status());assertNull(failed.results().getFirst().patch());assertNull(failed.results().getFirst().idiomaticValidation());
        Fixture missing=fixture(root.resolve("missing"),false);MethodBodyLoweringService noBackend=new MethodBodyLoweringService(TargetCapabilityMatrix.core("net8.0"),LoweringRuleRegistry.core("net8.0"),Map.of(),Map.of(),clock);RunResult result=noBackend.lower(request(missing,false,"strict"));assertEquals("manual-required",result.results().getFirst().status());assertTrue(result.results().getFirst().diagnostics().stream().anyMatch(value->value.startsWith("TARGET_AST_EMITTER_UNAVAILABLE")));
    }

    private MethodBodyLoweringService service(boolean validationPass){TargetEmitter emitter=request->{String indent=request.plan().targetLanguage().equals("python")?"    ":"    ";String body=indent+"Order result = findOrder();\n"+indent+"return result;";if(request.phase().equals("idiomatic"))body=indent+"return findOrder();";return new Emission(request.phase(),body,List.of(),request.plan().operations().stream().flatMap(value->value.generatedNodeIds().stream()).toList(),request.plan().operationIds(),List.of());};StaticValidator validator=request->new StaticValidation(request.plan().targetDeclarationId(),validationPass?Status.PASSED:Status.FAILED,validationPass?Status.PASSED:Status.NOT_RUN,validationPass?Status.PASSED:Status.NOT_RUN,validationPass?Status.PASSED:Status.NOT_RUN,validationPass?List.of():List.of("compiler-error"),List.of(),"test-compiler");return new MethodBodyLoweringService(TargetCapabilityMatrix.core("net8.0"),LoweringRuleRegistry.core("net8.0"),Map.of("csharp",emitter),Map.of("csharp",validator),clock);}
    private Request request(Fixture fixture,boolean agent,String fidelity){return new Request(fixture.workspace,fixture.uir,fixture.uirReport,fixture.skeleton,new GenerationProfile(fidelity,true,false,agent,true,"diagnostic",fidelity.equals("strict")?0:1),new Budgets(2,200,3));}
    private Fixture fixture(Path workspace,boolean opaque){UirModels.Dataset uir=uir(opaque);UirModels.ConformanceReport report=uirReport();SkeletonModels.TargetProfile profile=new SkeletonModels.TargetProfile("target-profile:csharp","csharp","exact","net8.0",null,"msbuild",List.of("container"),"library",List.of(),List.of(),Map.of(),true,List.of("no-preview"),List.of(),List.of());SkeletonModels.BuildBaseline baseline=new SkeletonModels.BuildBaseline(SkeletonModels.Status.PASSED,SkeletonModels.Status.PASSED,SkeletonModels.Status.PASSED,SkeletonModels.Status.PASSED,"sandbox:test",List.of(),List.of("compiler"));SkeletonModels.Result skeleton=new SkeletonGenerationService(clock,(repository,plan)->baseline).generate(workspace,uir,report,profile);return new Fixture(workspace,uir,report,skeleton);}
    private UirModels.Dataset uir(boolean opaque){String snapshot="snap",sem="sem",run="uir",module="uirmodule:orders",type="uirtype:order",method="uirdecl:find",region="region:body",block="block:body",call="uirop:call",ret="uirop:return",map="uirmap:call";UirModels.Provenance p=new UirModels.Provenance("prov","fixture","1",List.of(),List.of(),"fixture",Instant.EPOCH);List<UirModels.Entity>entities=new ArrayList<>();entities.add(entity("type",type,module,new UirModels.Type(type,"nominal","Order",null,List.of(),new UirModels.Nullability("non-null","source"),null,null,List.of(),null,List.of(),List.of(),"declared",1,Map.of()),p));entities.add(entity("declaration",method,module,new UirModels.Declaration(method,"method","findOrder","source.Order.findOrder",null,"public",List.of(),type,List.of(),List.of(),region,List.of("sym:find"),Map.of()),p));UirModels.Operation first=opaque?new UirModels.Operation(call,"uir.lang.python","opaque",List.of(),List.of(),Map.of("reason","fixture"),List.of(),List.of("effect:call"),List.of(map),new UirModels.Evaluation(List.of(),List.of(),false,true),.2):new UirModels.Operation(call,"uir.core","call",List.of(),List.of(new UirModels.Result("value:call",type)),Map.of(),List.of(),List.of("effect:call"),List.of(map),new UirModels.Evaluation(List.of("receiver","arguments"),List.of(),false,true),1);UirModels.Operation returning=new UirModels.Operation(ret,"uir.core","return",List.of("value:call"),List.of(),Map.of(),List.of(),List.of(),List.of(map),new UirModels.Evaluation(List.of("value:call"),List.of(),false,true),1);entities.add(entity("operation",call,module,first,p));entities.add(entity("operation",ret,module,returning,p));entities.add(entity("block",block,module,new UirModels.Block(block,List.of(),List.of(call,ret),ret,true),p));entities.add(entity("region",region,module,new UirModels.Region(region,"structured",List.of(block),block,null,null),p));entities.add(entity("module",module,module,new UirModels.Module(module,"orders","python",List.of(method),List.of(opaque?"uir.lang.python":"uir.core"),Map.of()),p));UirModels.Coverage coverage=new UirModels.Coverage(1,1,1,1,1,1,0,opaque?1:0,0,opaque?1:0);return new UirModels.Dataset(new UirModels.RunManifest(run,sem,snapshot,opaque?"completed_with_restrictions":"completed","1.0",List.of(module),List.of(),List.of(),"hash",coverage,List.of(),Instant.EPOCH),entities);}
    private UirModels.Entity entity(String kind,String id,String module,Object payload,UirModels.Provenance p){return new UirModels.Entity(kind,id,"snap","sem","uir",module,payload,p);}
    private UirModels.ConformanceReport uirReport(){UirModels.Coverage c=new UirModels.Coverage(1,1,1,1,1,1,0,0,0,0);return new UirModels.ConformanceReport(3,"passed",List.of(new UirModels.ModuleGate("uirmodule:orders","UIR-D",true,true,List.of(),c)),c,List.of(),List.of(),List.of(),List.of());}
    private record Fixture(Path workspace,UirModels.Dataset uir,UirModels.ConformanceReport uirReport,SkeletonModels.Result skeleton){}
}
