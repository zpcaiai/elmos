package io.elmos.workspaceservice;

import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.api.exception.NotFoundException;
import com.github.dockerjava.api.model.*;
import com.github.luben.zstd.ZstdInputStream;
import io.elmos.workspace.WorkspaceInfrastructurePorts;
import org.springframework.jdbc.core.simple.JdbcClient;

import java.io.*;
import java.nio.file.*;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.util.*;

final class DockerSnapshotVolumeMaterializer implements WorkspaceInfrastructurePorts.SnapshotVolumeMaterializer {
    private record Archive(String reference,String sha256,long size){}
    private final DockerClient docker;private final JdbcClient jdbc;private final Path artifactRoot;private final String helperImageDigest;
    private final WorkspaceInfrastructurePorts.ApprovedImageRegistry images;
    DockerSnapshotVolumeMaterializer(DockerClient docker,JdbcClient jdbc,Path artifactRoot,String helperImageDigest,WorkspaceInfrastructurePorts.ApprovedImageRegistry images){
        this.docker=docker;this.jdbc=jdbc;this.artifactRoot=artifactRoot.toAbsolutePath().normalize();this.helperImageDigest=helperImageDigest;this.images=images;
        if(!helperImageDigest.matches("sha256:[0-9a-f]{64}"))throw new IllegalArgumentException("snapshot helper image digest is required");
    }
    @Override public void materialize(String snapshotId,String snapshotVolume,String workspaceVolume){
        Archive archive=jdbc.sql("select archive_artifact_ref,archive_sha256,archive_size from repository_snapshots where snapshot_id=:id and status='AVAILABLE'")
                .param("id",snapshotId).query((rs,row)->new Archive(rs.getString(1),rs.getString(2),rs.getLong(3))).single();
        Path path=artifactPath(archive.reference());try{if(Files.isSymbolicLink(path)||Files.size(path)!=archive.size())throw new SecurityException("snapshot artifact metadata mismatch");}
        catch(IOException error){throw new IllegalArgumentException("snapshot archive is unavailable",error);}
        images.requireApproved("snapshot-materializer",helperImageDigest);
        HostConfig host=HostConfig.newHostConfig().withPrivileged(false).withReadonlyRootfs(true).withCapDrop(Capability.ALL)
                .withSecurityOpts(List.of("no-new-privileges:true")).withNetworkMode("none").withMemory(256L*1024*1024).withMemorySwap(256L*1024*1024)
                .withNanoCPUs(250_000_000L).withPidsLimit(64L).withTmpFs(Map.of("/tmp","rw,noexec,nosuid,size=64m"))
                .withBinds(new Bind(snapshotVolume,new Volume("/snapshot"),com.github.dockerjava.api.model.AccessMode.rw),new Bind(workspaceVolume,new Volume("/workspace"),com.github.dockerjava.api.model.AccessMode.rw));
        String helper=docker.createContainerCmd(helperImageDigest).withName("elmos-materialize-"+UUID.randomUUID()).withUser("10001:10001").withCmd("sleep","60")
                .withHostConfig(host).withLabels(Map.of("elmos.managed","true","elmos.resource_role","snapshot-materializer","elmos.retention","ephemeral")).exec().getId();
        try{docker.startContainerCmd(helper).exec();copy(helper,"/snapshot",path,archive);copy(helper,"/workspace",path,archive);}
        finally{try{docker.removeContainerCmd(helper).withForce(true).exec();}catch(NotFoundException ignored){}}
    }
    private void copy(String container,String target,Path path,Archive archive){
        try{MessageDigest digest=MessageDigest.getInstance("SHA-256");
            try(InputStream raw=Files.newInputStream(path);DigestInputStream verified=new DigestInputStream(raw,digest);InputStream tar=new ZstdInputStream(verified)){
                docker.copyArchiveToContainerCmd(container).withRemotePath(target).withTarInputStream(tar).withCopyUIDGID(true).withDirChildrenOnly(true).exec();
            }
            String actual=HexFormat.of().formatHex(digest.digest());if(!actual.equals(archive.sha256()))throw new SecurityException("snapshot archive digest mismatch");
        }catch(RuntimeException error){throw error;}catch(Exception error){throw new IllegalStateException("snapshot materialization failed",error);}
    }
    private Path artifactPath(String reference){if(reference==null||!reference.matches("cas:sha256:[0-9a-f]{64}"))throw new SecurityException("unsupported snapshot artifact reference");String sha=reference.substring("cas:sha256:".length());Path path=artifactRoot.resolve(sha.substring(0,2)).resolve(sha.substring(2,4)).resolve(sha).normalize();if(!path.startsWith(artifactRoot))throw new SecurityException("snapshot artifact path escape");return path;}
}
