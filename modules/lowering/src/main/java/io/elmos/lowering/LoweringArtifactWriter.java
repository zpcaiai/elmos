package io.elmos.lowering;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.io.IOException;
import java.nio.file.*;
import java.util.List;

import static io.elmos.lowering.LoweringModels.*;

public final class LoweringArtifactWriter {
    private final ObjectMapper json=new ObjectMapper().findAndRegisterModules().enable(SerializationFeature.INDENT_OUTPUT).enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    public void write(Path workspace,RunResult result,List<Capability> capabilities,List<Rule> rules){
        try{
            Path root=workspace.toRealPath(LinkOption.NOFOLLOW_LINKS);for(String path:List.of("lowering/capability-matrix","lowering/rule-registry","lowering/plans","lowering/results","lowering/helpers","lowering/agent-packets","lowering/diagnostics","mappings","patches/callable-patches","patches/helper-patches","patches/rejected","patches/conflicts","reports","logs/lowering","logs/emission","logs/formatting","logs/validation","logs/agent"))Files.createDirectories(root.resolve(path));
            write(root.resolve("lowering/lowering-run-manifest.json"),result.manifest());write(root.resolve("lowering/capability-matrix/"+result.manifest().targetLanguage()+".json"),capabilities);write(root.resolve("lowering/rule-registry/rules.json"),rules);
            for(CallablePlan plan:result.plans())write(root.resolve("lowering/plans/"+safe(plan.targetDeclarationId())+".json"),plan);
            for(CallableResult value:result.results()){
                write(root.resolve("lowering/results/"+safe(value.targetDeclarationId())+".json"),value);
                if(value.patch()!=null)write(root.resolve("patches/callable-patches/"+safe(value.patch().patchId())+".json"),value.patch());
                if(value.agentPacket()!=null)write(root.resolve("lowering/agent-packets/"+safe(value.agentPacket().taskId())+".json"),value.agentPacket());
            }
            writeJsonl(root.resolve("mappings/uir-target-operations.jsonl"),result.plans().stream().flatMap(plan->plan.operations().stream()).toList());writeJsonl(root.resolve("mappings/target-temporaries.jsonl"),result.plans().stream().flatMap(plan->plan.temporaries().stream()).toList());
            write(root.resolve("reports/generation-coverage-report.json"),result.conformance().coverage());write(root.resolve("reports/static-validation-report.json"),result.results().stream().map(CallableResult::faithfulValidation).filter(java.util.Objects::nonNull).toList());write(root.resolve("reports/agent-escalation-report.json"),result.results().stream().map(CallableResult::agentPacket).filter(java.util.Objects::nonNull).toList());write(root.resolve("reports/batch-5-conformance-report.json"),result.conformance());
            for(String report:List.of("type-mapping-report.json","numeric-semantics-report.json","collection-semantics-report.json","exception-mapping-report.json","async-mapping-report.json","nullability-report.json"))write(root.resolve("reports/"+report),result.conformance().fidelity());
        }catch(IOException error){throw new IllegalStateException("LOWERING_ARTIFACT_WRITE_FAILED",error);}
    }
    private void write(Path path,Object value)throws IOException{byte[]bytes=json.writeValueAsBytes(value);atomic(path,bytes);}
    private void writeJsonl(Path path,List<?> values)throws IOException{StringBuilder out=new StringBuilder();for(Object value:values)out.append(json.writer().without(SerializationFeature.INDENT_OUTPUT).writeValueAsString(value)).append('\n');atomic(path,out.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));}
    private static void atomic(Path path,byte[]bytes)throws IOException{Files.createDirectories(path.getParent());Path temporary=Files.createTempFile(path.getParent(),path.getFileName().toString(),".tmp");try{Files.write(temporary,bytes);Files.move(temporary,path,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}finally{Files.deleteIfExists(temporary);}}
    private static String safe(String value){return value.replaceAll("[^A-Za-z0-9._-]","-");}
}
