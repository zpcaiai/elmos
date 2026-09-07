package io.elmos.workspaceservice;

import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.core.command.ExecStartResultCallback;
import io.elmos.secret.SecretInjectionService;
import io.elmos.secret.SecretValue;
import org.apache.commons.compress.archivers.tar.TarArchiveEntry;
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.TimeUnit;

final class DockerTmpfsSecretMaterializer implements SecretInjectionService.SecretMaterializerPort {
    private final DockerClient docker;private final WorkspaceSecretRegistry registry;
    DockerTmpfsSecretMaterializer(DockerClient docker,WorkspaceSecretRegistry registry){this.docker=docker;this.registry=registry;}
    @Override public void materializeReadOnlyTmpfs(String workspaceId,String leaseId,SecretValue value){
        validate(workspaceId,leaseId);String container=container(workspaceId);WipingBuffer buffer=new WipingBuffer();
        try{value.use(chars->{byte[] bytes=utf8(chars);try(TarArchiveOutputStream tar=new TarArchiveOutputStream(buffer)){TarArchiveEntry entry=new TarArchiveEntry(fileName(leaseId));entry.setSize(bytes.length);entry.setMode(0400);entry.setUserId(10001);entry.setGroupId(10001);entry.setUserName("elmos");entry.setGroupName("elmos");entry.setModTime(0);tar.putArchiveEntry(entry);tar.write(bytes);tar.closeArchiveEntry();tar.finish();}catch(IOException error){throw new UncheckedIOException(error);}finally{Arrays.fill(bytes,(byte)0);}return null;});
            try(InputStream input=buffer.input()){docker.copyArchiveToContainerCmd(container).withRemotePath("/run/secrets").withTarInputStream(input).withCopyUIDGID(true).withDirChildrenOnly(true).exec();}
            value.use(chars->{registry.register(workspaceId,leaseId,chars);return null;});
        }catch(IOException error){throw new IllegalStateException("secret tmpfs materialization failed",error);}finally{buffer.wipe();}
    }
    @Override public void remove(String workspaceId,String leaseId){validate(workspaceId,leaseId);String container=container(workspaceId);
        var created=docker.execCreateCmd(container).withAttachStdout(false).withAttachStderr(false).withPrivileged(false).withUser("10001:10001").withCmd("rm","-f","/run/secrets/"+fileName(leaseId)).exec();
        try{boolean done=docker.execStartCmd(created.getId()).exec(new ExecStartResultCallback(OutputStream.nullOutputStream(),OutputStream.nullOutputStream())).awaitCompletion(10,TimeUnit.SECONDS);if(!done)throw new IllegalStateException("secret removal timed out");Long exit=docker.inspectExecCmd(created.getId()).exec().getExitCodeLong();if(exit==null||exit!=0)throw new IllegalStateException("secret removal failed");registry.remove(workspaceId,leaseId);}catch(InterruptedException error){Thread.currentThread().interrupt();throw new IllegalStateException("secret removal interrupted",error);}
    }
    private String container(String workspaceId){var containers=docker.listContainersCmd().withShowAll(true).withLabelFilter(Map.of("elmos.workspace_id",workspaceId,"elmos.resource_role","container","elmos.managed","true")).exec();if(containers.size()!=1)throw new IllegalStateException("workspace container identity is missing or ambiguous");return containers.getFirst().getId();}
    private static void validate(String workspace,String lease){if(workspace==null||!workspace.matches("[A-Za-z0-9._:-]{1,64}")||lease==null||!lease.matches("[A-Za-z0-9._:-]{1,64}"))throw new IllegalArgumentException("secret binding identity is invalid");}
    private static String fileName(String lease){return "elmos-secret-"+lease;}
    private static byte[] utf8(char[] chars){java.nio.ByteBuffer encoded=StandardCharsets.UTF_8.encode(java.nio.CharBuffer.wrap(chars));byte[] result=new byte[encoded.remaining()];encoded.get(result);return result;}
    private static final class WipingBuffer extends ByteArrayOutputStream{InputStream input(){return new ByteArrayInputStream(buf,0,count);}void wipe(){Arrays.fill(buf,(byte)0);reset();}}
}
