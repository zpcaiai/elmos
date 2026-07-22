package io.elmos.workspaceservice;

import io.elmos.workspace.WorkspaceInfrastructurePorts;
import org.springframework.jdbc.core.simple.JdbcClient;

import java.nio.file.*;
import java.security.MessageDigest;
import java.util.HexFormat;

final class FileCommandArtifactStore implements WorkspaceInfrastructurePorts.CommandArtifactStore {
    private final Path root; private final JdbcClient jdbc;
    FileCommandArtifactStore(Path root,JdbcClient jdbc){this.root=root.toAbsolutePath().normalize();this.jdbc=jdbc;try{Files.createDirectories(this.root);}catch(Exception error){throw new IllegalArgumentException("command artifact root is unavailable",error);}}
    @Override public String store(String workspaceId,String commandId,String stream,byte[] bytes){
        if(!workspaceId.matches("[A-Za-z0-9._:-]{1,64}")||!commandId.matches("[A-Za-z0-9._:-]{1,64}")||!stream.matches("stdout|stderr")||bytes.length>10*1024*1024)throw new IllegalArgumentException("command artifact identity is invalid");
        String digest=sha(bytes);Path path=root.resolve(digest.substring(0,2)).resolve(digest).normalize();if(!path.startsWith(root))throw new SecurityException("artifact path escape");
        try{Files.createDirectories(path.getParent());if(Files.exists(path)){if(Files.isSymbolicLink(path)||!sha(Files.readAllBytes(path)).equals(digest))throw new SecurityException("artifact collision");}
            else{Path temporary=Files.createTempFile(path.getParent(),".artifact-",".tmp");try{Files.write(temporary,bytes,StandardOpenOption.TRUNCATE_EXISTING);Files.move(temporary,path,StandardCopyOption.ATOMIC_MOVE);}finally{Files.deleteIfExists(temporary);}}}
        catch(RuntimeException error){throw error;}catch(Exception error){throw new IllegalStateException("command artifact store failed",error);}
        String ref="workspace-cas:sha256:"+digest;String artifactId="artifact-"+sha(workspaceId+"\0"+commandId+"\0"+stream).substring(0,48);
        jdbc.sql("insert into workspace_artifacts(workspace_artifact_id,workspace_id,artifact_type,artifact_ref,sha256,size_bytes,secret_scan_status,created_at) values(:id,:workspace,:type,:ref,:sha,:size,'PASS',current_timestamp) on conflict (workspace_id,artifact_type,sha256) do nothing")
                .param("id",artifactId).param("workspace",workspaceId).param("type","COMMAND_"+stream.toUpperCase()).param("ref",ref).param("sha",digest).param("size",bytes.length).update();return ref;
    }
    private static String sha(byte[] bytes){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));}catch(Exception error){throw new IllegalStateException(error);}}
    private static String sha(String value){return sha(value.getBytes(java.nio.charset.StandardCharsets.UTF_8));}
}
