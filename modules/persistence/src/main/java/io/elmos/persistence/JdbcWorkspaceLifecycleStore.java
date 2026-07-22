package io.elmos.persistence;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.workspace.WorkspaceInfrastructurePorts;
import io.elmos.workspace.WorkspaceModels;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;

public final class JdbcWorkspaceLifecycleStore implements WorkspaceInfrastructurePorts.WorkspaceLifecycleStore {
    private final JdbcClient jdbc; private final ObjectMapper json; private final Clock clock;
    public JdbcWorkspaceLifecycleStore(JdbcClient jdbc,ObjectMapper json,Clock clock){this.jdbc=jdbc;this.json=json;this.clock=clock;}
    @Override @Transactional public void requested(WorkspaceModels.WorkspaceRequest request){
        int changed=jdbc.sql("insert into workspace_instances(workspace_id,workspace_external_id,organization_id,migration_run_id,snapshot_id,sandbox_profile_id,image_digest,state,resource_limits,network_policy_id,created_at,last_heartbeat_at,expires_at) values(:id,:external,:org,:run,:snapshot,:profile,:image,'PROVISIONING',cast(:limits as jsonb),:policy,:now,:now,:expires) on conflict (workspace_id) do nothing")
                .param("id",request.workspaceId()).param("external","pending-"+request.workspaceId()).param("org",request.organizationId()).param("run",request.migrationRunId())
                .param("snapshot",request.snapshotId()).param("profile",request.sandboxProfile()).param("image",request.imageDigest()).param("limits",toJson(request.resources()))
                .param("policy",request.networkPolicyId()).param("now",clock.instant()).param("expires",clock.instant().plus(request.resources().workspaceTimeout())).update();
        if(changed==0){String identity=jdbc.sql("select snapshot_id||':'||image_digest from workspace_instances where workspace_id=:id").param("id",request.workspaceId()).query(String.class).single();
            if(!identity.equals(request.snapshotId()+":"+request.imageDigest()))throw new SecurityException("workspace idempotency identity collision");}
    }
    @Override @Transactional public void ready(WorkspaceModels.WorkspaceRequest request,String containerId,String networkId,Map<String,String> volumes){
        jdbc.sql("update workspace_instances set workspace_external_id=:external,state='READY',last_heartbeat_at=:now where workspace_id=:id")
                .param("external",containerId).param("now",clock.instant()).param("id",request.workspaceId()).update();
        for(var entry:volumes.entrySet())jdbc.sql("insert into workspace_mounts(mount_id,workspace_id,volume_external_id,role,container_path,read_only,ownership_labels) values(:mount,:workspace,:volume,:role,:path,:readOnly,cast(:labels as jsonb)) on conflict (workspace_id,container_path) do nothing")
                .param("mount",id("mount",request.workspaceId()+":"+entry.getKey())).param("workspace",request.workspaceId()).param("volume",entry.getValue()).param("role",entry.getKey())
                .param("path",containerPath(entry.getKey())).param("readOnly",entry.getKey().equals("snapshot")).param("labels",toJson(Map.of("elmos.managed","true","elmos.workspace_id",request.workspaceId()))).update();
    }
    @Override @Transactional public void commandStarted(String workspaceId,WorkspaceModels.WorkspaceCommand command,String argvSha256,Instant startedAt){
        int changed=jdbc.sql("insert into workspace_commands(command_id,workspace_id,idempotency_key,argv_sha256,working_directory,status,started_at) values(:command,:workspace,:key,:sha,:directory,'RUNNING',:started) on conflict (workspace_id,idempotency_key) do nothing")
                .param("command",command.commandId()).param("workspace",workspaceId).param("key",command.commandId()).param("sha",argvSha256).param("directory",command.workingDirectory()).param("started",startedAt).update();
        if(changed==0){String existing=jdbc.sql("select argv_sha256 from workspace_commands where workspace_id=:workspace and idempotency_key=:key").param("workspace",workspaceId).param("key",command.commandId()).query(String.class).single();if(!existing.equals(argvSha256))throw new SecurityException("command idempotency identity collision");}
        jdbc.sql("update workspace_instances set state='EXECUTING',last_heartbeat_at=:now where workspace_id=:id").param("now",startedAt).param("id",workspaceId).update();
    }
    @Override @Transactional public void commandFinished(String workspaceId,WorkspaceModels.CommandResult result){
        jdbc.sql("update workspace_commands set status=:status,finished_at=:finished,exit_code=:exit,termination_reason=:reason,stdout_artifact_ref=:stdout,stderr_artifact_ref=:stderr,output_sha256=:sha,output_truncated=:truncated where command_id=:command and workspace_id=:workspace")
                .param("status",result.terminationReason().equals("COMPLETED")?"COMPLETED":"FAILED").param("finished",result.finishedAt()).param("exit",result.exitCode()).param("reason",result.terminationReason())
                .param("stdout",result.stdoutArtifactRef()).param("stderr",result.stderrArtifactRef()).param("sha",result.outputSha256()).param("truncated",result.outputTruncated()).param("command",result.commandId()).param("workspace",workspaceId).update();
        jdbc.sql("update workspace_instances set state='READY',last_heartbeat_at=:now where workspace_id=:id").param("now",result.finishedAt()).param("id",workspaceId).update();
    }
    @Override public void terminated(String workspaceId,WorkspaceModels.TerminationReason reason,Instant at){
        jdbc.sql("update workspace_instances set state='TERMINATED',terminated_at=:at,last_heartbeat_at=:at where workspace_id=:id").param("at",at).param("id",workspaceId).update();
        jdbc.sql("insert into workspace_events(workspace_event_id,workspace_id,event_type,occurred_at,attributes) values(:event,:workspace,'TERMINATED',:at,cast(:attributes as jsonb)) on conflict do nothing")
                .param("event",id("terminated",workspaceId)).param("workspace",workspaceId).param("at",at).param("attributes",toJson(Map.of("reason",reason.name()))).update();
    }
    private String toJson(Object value){try{return json.writeValueAsString(value);}catch(JsonProcessingException error){throw new IllegalArgumentException("workspace metadata is not serializable",error);}}
    private static String containerPath(String role){return switch(role){case"snapshot"->"/input/snapshot";case"workspace"->"/workspace";case"artifacts"->"/artifacts";case"maven-cache"->"/home/elmos/.m2";default->throw new IllegalArgumentException("unknown volume role");};}
    private static String id(String prefix,String value){try{return prefix+"-"+HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))).substring(0,48);}catch(Exception error){throw new IllegalStateException(error);}}
}
