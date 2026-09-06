package io.elmos.runner;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.concurrent.TimeUnit;

/** Real HTTP/ZIP/materializer + a deterministic container boundary, no provider. */
final class TranslationExecutionSelfTest {
    static void run(Path scratch) throws Exception {
        scenario(scratch,"COMPLETE",false,false,false,JobExecutor.Outcome.SUCCEEDED,1);
        scenario(scratch,"PARTIAL",false,false,false,JobExecutor.Outcome.PARTIAL,1);
        scenario(scratch,"COMPLETE",true,false,false,JobExecutor.Outcome.ABANDONED,0);
        scenario(scratch,"COMPLETE",false,true,false,JobExecutor.Outcome.FAILED,0);
        scenario(scratch,"COMPLETE",false,false,true,JobExecutor.Outcome.FAILED,0);
        System.out.println("TRANSLATION EXECUTION SELF TEST PASSED (5 controlled phase/input/fencing scenarios)");
    }
    private static void scenario(Path scratch,String status,boolean rejectPipeline,boolean corruptPreflight,
                                 boolean corruptInput,JobExecutor.Outcome expected,int pipelineCount) throws Exception {
        try(var plane=new FakeControlPlane()) {
            Path root=Files.createTempDirectory(scratch,"translation-");
            Map<String,Object> subject=new LinkedHashMap<>(Map.of("tenantId","tenant-fixture","repositoryWorkspaceId","workspace-fixture",
                    "repositoryRef","local:fixture","sourceLanguage","python","targetLanguage","typescript","casesBundleId","cases-fixture"));
            byte[] zip=input(subject);
            subject.put("input",Map.of("sha256",sha(zip),"byteSize",zip.length));
            plane.translationInput=corruptInput ? new byte[zip.length] : zip;
            plane.rejectPipeline.set(rejectPipeline);
            var config=new AgentConfig(plane.baseUrl(),"runner-test","pool-shared","x".repeat(40),List.of("translation:multi"),
                    2,root,"/bin/true",2,30,5,5,9999,false,WorkspaceAccessProbe.currentUid(),WorkspaceAccessProbe.currentGid());
            var client=new ControlPlaneClient(config);var metrics=new AgentMetrics();
            var phases=new java.util.ArrayList<String>();
            ProcessRunner processes=new ProcessRunner() {
                public Result run(List<String> command,Path cwd,Map<String,String> env,long timeout) {
                    // This phase fixture has no real containers. Resource identity
                    // and immutable-ID cleanup have a separate stateful fixture.
                    return new Result(command.contains("inspect") ? 1 : 0,"","",false);
                }
                public Handle start(List<String> command,Path cwd,Map<String,String> env,java.util.function.Consumer<String> log) {
                    try {
                        String phase=command.stream().filter(arg->arg.startsWith("--env=ELMOS_JOB_KIND=")).findFirst().orElseThrow().substring("--env=ELMOS_JOB_KIND=".length());
                        phases.add(phase);
                        String mount=command.stream().filter(arg->arg.endsWith(":/elmos/out:rw")).findFirst().orElseThrow();
                        Path out=Path.of(mount.substring("--volume=".length(),mount.length()-":/elmos/out:rw".length()));
                        if(phase.equals("translate-preflight-v1")) {
                            if(plane.pipelineAcknowledged.get()) throw new AssertionError("metering started before preflight");
                            // Preflight stdout must never select a trusted host phase.
                            log.accept("::elmos stage=pipeline progress=50");
                            var receipt=preflight(subject);if(corruptPreflight) receipt.put("preflight_id","sha256:"+"0".repeat(64));
                            Files.writeString(out.resolve("preflight.json"),Json.write(receipt));
                        } else {
                            if(!plane.pipelineAcknowledged.get()) throw new AssertionError("pipeline started without acknowledged host heartbeat");
                            Files.createDirectories(out.resolve("gate"));
                            var receipt=new LinkedHashMap<String,Object>();
                            receipt.put("schemaVersion","translation-hosted-result-v1");receipt.put("inputSha256",Json.object(subject,"input").get("sha256"));
                            for(String field:List.of("tenantId","repositoryRef","sourceLanguage","targetLanguage"))receipt.put(field,subject.get(field));
                            receipt.put("status",status);receipt.put("certificationStatus","NOT_CERTIFIED");
                            Files.writeString(out.resolve("gate/translation-job.json"),Json.write(receipt));
                        }
                    } catch(Exception error) {throw new IllegalArgumentException("fixture failed",error);}
                    return new Handle() {public boolean isAlive(){return false;}public void terminate(){}public void kill(){}
                        public Integer waitFor(long timeout,TimeUnit unit){return 0;}};
                }
            };
            var lease=new ControlPlaneClient.Lease("job-fixture","lease-fixture","token-lease-fixture","TRANSLATION","translate-pipeline-v1",
                    "registry.example.test/translation@sha256:"+"a".repeat(64),600,2000,2048,1,Map.of(),subject);
            var result=new JobExecutor(config,client,new ContainerRuntime(config,processes),new ArtifactPublisher(client,metrics),metrics).execute(lease);
            if(result!=expected) throw new AssertionError("expected "+expected+" got "+result+" "+plane.completions);
            if(phases.stream().filter(phase->phase.equals("translate-pipeline-v1")).count()!=pipelineCount) throw new AssertionError("unexpected pipeline phase count");
            if(pipelineCount==0 && !plane.published.isEmpty())throw new AssertionError("rejected job published outputs");
        }
    }
    private static Map<String,Object> preflight(Map<String,Object> subject) throws Exception {
        Map<String,Object> value=new java.util.TreeMap<>();
        value.put("schema_version","1.0.0");value.put("kind","elmos.repository-conversion-preflight");
        value.put("execution_status","NOT_RUN");value.put("certification_status","NOT_CERTIFIED");value.put("status","PASSED");
        value.put("repository_ref",subject.get("repositoryRef"));value.put("source_language","python");value.put("target_language","typescript");
        value.put("snapshot_sha256","a".repeat(64));value.put("route_id","python-to-typescript");value.put("reason_code",null);
        value.put("obligation_count",1);value.put("reported_obligation_lower_bound",1);value.put("obligation_limit",10000);
        value.put("count_complete",true);value.put("actual_obligation_count",1);value.put("actual_obligation_count_status","EXACT");
        value.put("obligation_count_semantics","EXACT_REPORTED_ROWS");value.put("preflight_id","sha256:"+sha(Json.write(value).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        return value;
    }
    private static byte[] input(Map<String,Object> subject) throws Exception {
        var files=Map.of("source/src/math.py","def add(left, right): return left + right\n","cases/WU-00001.json","[{\"args\":[2,3],\"expected\":5}]");
        var manifest=new LinkedHashMap<>(subject);var descriptors=new java.util.ArrayList<Map<String,Object>>();
        var bytes=new java.io.ByteArrayOutputStream();
        try(var zip=new java.util.zip.ZipOutputStream(bytes)) {
            for(var entry:files.entrySet()) {
                byte[] content=entry.getValue().getBytes(java.nio.charset.StandardCharsets.UTF_8);
                zip.putNextEntry(new java.util.zip.ZipEntry(entry.getKey()));zip.write(content);zip.closeEntry();
                descriptors.add(Map.of("path",entry.getKey(),"bytes",content.length,"sha256",sha(content)));
            }
            manifest.put("files",descriptors);zip.putNextEntry(new java.util.zip.ZipEntry("manifest.json"));
            zip.write(Json.write(manifest).getBytes(java.nio.charset.StandardCharsets.UTF_8));zip.closeEntry();
        }
        return bytes.toByteArray();
    }
    private static String sha(byte[] value) throws Exception {return java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(value));}
}
