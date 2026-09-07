package io.elmos.workspaceservice;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.api.async.ResultCallback;
import com.github.dockerjava.api.model.*;
import io.elmos.workspace.WorkspaceInfrastructurePorts;
import io.elmos.workspace.WorkspaceModels;
import org.springframework.jdbc.core.simple.JdbcClient;

import java.io.Closeable;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.concurrent.TimeUnit;

final class DockerNetworkPolicyEnforcer implements WorkspaceInfrastructurePorts.NetworkPolicyEnforcer {
    private record Policy(int version,OffsetDateTime expiresAt,List<String> hosts){}
    private final DockerClient docker;private final JdbcClient jdbc;private final ObjectMapper json;private final String proxyImageDigest;
    private final WorkspaceInfrastructurePorts.ApprovedImageRegistry images;
    DockerNetworkPolicyEnforcer(DockerClient docker,JdbcClient jdbc,ObjectMapper json,String proxyImageDigest,WorkspaceInfrastructurePorts.ApprovedImageRegistry images){this.docker=docker;this.jdbc=jdbc;this.json=json;this.proxyImageDigest=proxyImageDigest;this.images=images;if(!proxyImageDigest.matches("sha256:[0-9a-f]{64}"))throw new IllegalArgumentException("egress proxy image digest is required");}
    @Override public WorkspaceInfrastructurePorts.NetworkBinding apply(WorkspaceModels.WorkspaceRequest request,String networkId,String networkName){
        Policy policy=load(request);String bindingId="binding-"+digest(request.workspaceId()).substring(0,48);String proxyId=null,proxyUrl=null;
        if(!policy.hosts().isEmpty()){
            images.requireApproved("egress-proxy",proxyImageDigest);String name="elmos-egress-"+digest(request.workspaceId()).substring(0,20);
            HostConfig host=HostConfig.newHostConfig().withPrivileged(false).withReadonlyRootfs(true).withCapDrop(Capability.ALL).withSecurityOpts(List.of("no-new-privileges:true"))
                    .withNetworkMode(networkName).withMemory(256L*1024*1024).withMemorySwap(256L*1024*1024).withNanoCPUs(250_000_000L).withPidsLimit(128L).withTmpFs(Map.of("/tmp","rw,noexec,nosuid,size=32m"));
            proxyId=docker.createContainerCmd(proxyImageDigest).withName(name).withHostName(name).withUser("10001:10001").withHostConfig(host)
                    .withEnv("ELMOS_WORKSPACE_ID="+request.workspaceId(),"ELMOS_NETWORK_POLICY_ID="+request.networkPolicyId(),"ELMOS_NETWORK_POLICY_VERSION="+policy.version(),"ELMOS_EGRESS_ALLOWED_HOSTS="+String.join(",",policy.hosts()))
                    .withLabels(Map.of("elmos.managed","true","elmos.organization_id",request.organizationId(),"elmos.workspace_id",request.workspaceId(),"elmos.resource_role","egress-proxy","elmos.retention","ephemeral")).exec().getId();
            docker.startContainerCmd(proxyId).exec();docker.connectToNetworkCmd().withContainerId(proxyId).withNetworkId("bridge").exec();proxyUrl="http://"+name+":8080";
        }
        jdbc.sql("insert into network_policy_bindings(binding_id,workspace_id,network_policy_id,policy_version,proxy_external_id,applied_at) values(:binding,:workspace,:policy,:version,:proxy,current_timestamp)")
                .param("binding",bindingId).param("workspace",request.workspaceId()).param("policy",request.networkPolicyId()).param("version",policy.version()).param("proxy",proxyId).update();
        return new WorkspaceInfrastructurePorts.NetworkBinding(bindingId,proxyUrl,proxyId);
    }
    @Override public void collectAndRemove(String workspaceId){
        var binding=jdbc.sql("select binding_id from network_policy_bindings where workspace_id=:workspace and removed_at is null order by applied_at desc limit 1").param("workspace",workspaceId).query(String.class).optional();
        if(binding.isEmpty())return;for(var container:docker.listContainersCmd().withShowAll(true).withLabelFilter(Map.of("elmos.workspace_id",workspaceId,"elmos.resource_role","egress-proxy","elmos.managed","true")).exec())collect(container.getId(),binding.get());
        jdbc.sql("update network_policy_bindings set removed_at=current_timestamp where binding_id=:binding and removed_at is null").param("binding",binding.get()).update();
    }
    private Policy load(WorkspaceModels.WorkspaceRequest request){
        int version=jdbc.sql("select policy_version from network_policies where network_policy_id=:id and status='APPROVED' and valid_from<=current_timestamp and (expires_at is null or expires_at>current_timestamp) and (organization_id is null or organization_id=:org) order by policy_version desc limit 1")
                .param("id",request.networkPolicyId()).param("org",request.organizationId()).query(Integer.class).optional().orElseThrow(()->new SecurityException("approved active network policy is required"));
        List<String> hosts=jdbc.sql("select exact_host from network_policy_rules where network_policy_id=:id and policy_version=:version order by rule_order")
                .param("id",request.networkPolicyId()).param("version",version).query(String.class).list();return new Policy(version,null,hosts);
    }
    private void collect(String containerId,String bindingId){
        StringBuilder output=new StringBuilder();ResultCallback.Adapter<Frame> callback=new ResultCallback.Adapter<>(){@Override public void onNext(Frame frame){if(output.length()<10*1024*1024)output.append(new String(frame.getPayload(),StandardCharsets.UTF_8));}};
        try{docker.logContainerCmd(containerId).withStdOut(true).withStdErr(false).withTailAll().exec(callback).awaitCompletion(10, TimeUnit.SECONDS);}
        catch(InterruptedException error){Thread.currentThread().interrupt();throw new IllegalStateException("proxy audit collection interrupted",error);}finally{try{callback.close();}catch(Exception ignored){}}
        int index=0;for(String line:output.toString().lines().toList()){JsonNode event;try{event=json.readTree(line);}catch(Exception invalid){continue;}String host=event.path("host").asText();String decision=event.path("decision").asText();if(!host.matches("[A-Za-z0-9.-]{1,253}")||!(decision.equals("ALLOW")||decision.equals("DENY")))continue;
            jdbc.sql("insert into network_access_events(access_event_id,binding_id,occurred_at,scheme,host,resolved_addresses,decision,reason,bytes_sent,bytes_received) values(:id,:binding,current_timestamp,'HTTPS',:host,cast(:addresses as jsonb),:decision,:reason,:sent,:received) on conflict do nothing")
                    .param("id","access-"+digest(bindingId+":"+(index++)+":"+line).substring(0,48)).param("binding",bindingId).param("host",host).param("addresses",event.path("resolvedAddresses").toString())
                    .param("decision",decision).param("reason",event.path("reason").asText("unknown")).param("sent",event.path("bytesSent").asLong()).param("received",event.path("bytesReceived").asLong()).update();
        }
    }
    private static String digest(String value){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));}catch(Exception error){throw new IllegalStateException(error);}}
}
