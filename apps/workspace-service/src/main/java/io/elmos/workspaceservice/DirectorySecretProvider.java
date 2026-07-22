package io.elmos.workspaceservice;

import io.elmos.secret.SecretInjectionService;
import io.elmos.secret.SecretValue;

import java.io.Reader;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermission;
import java.time.Clock;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

final class DirectorySecretProvider implements SecretInjectionService.SecretProviderPort {
    private final Path root;private final Clock clock;private final Map<String,Path> leases=new ConcurrentHashMap<>();
    DirectorySecretProvider(Path root,Clock clock){this.root=root.toAbsolutePath().normalize();this.clock=clock;try{Files.createDirectories(this.root);}catch(Exception error){throw new IllegalArgumentException("provider secret root is unavailable",error);}}
    @Override public SecretInjectionService.ProviderLease issue(SecretInjectionService.SecretRequest request){String name=request.workspaceId()+"."+request.type().name()+".secret";Path path=root.resolve(name).normalize();if(!path.startsWith(root)||Files.isSymbolicLink(path)||!Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS))throw new SecurityException("provider secret file is unavailable");
        verifyPermissions(path);char[] value=read(path);String providerId="file-lease-"+UUID.randomUUID();leases.put(providerId,path);var issued=clock.instant();
        try{return new SecretInjectionService.ProviderLease(providerId,new SecretValue(value),issued,issued.plus(request.requestedTtl()));}
        finally{Arrays.fill(value,'\0');}}
    @Override public void revoke(String providerLeaseId){Path path=leases.remove(providerLeaseId);if(path==null)return;if(!path.startsWith(root)||Files.isSymbolicLink(path))throw new SecurityException("provider lease path escape");try{long size=Files.size(path);try(var output=Files.newOutputStream(path,StandardOpenOption.WRITE,StandardOpenOption.TRUNCATE_EXISTING)){byte[] zeros=new byte[8192];for(long written=0;written<size;written+=zeros.length)output.write(zeros,0,(int)Math.min(zeros.length,size-written));output.flush();}Files.deleteIfExists(path);}catch(Exception error){throw new IllegalStateException("provider secret revocation failed",error);}}
    private static void verifyPermissions(Path path){try{Set<PosixFilePermission> permissions=Files.getPosixFilePermissions(path,LinkOption.NOFOLLOW_LINKS);if(permissions.stream().anyMatch(value->value.name().startsWith("GROUP_")||value.name().startsWith("OTHERS_")))throw new SecurityException("provider secret file must be owner-only");}catch(UnsupportedOperationException ignored){}catch(java.io.IOException error){throw new IllegalArgumentException("provider secret permissions unavailable",error);}}
    private static char[] read(Path path){try(Reader reader=Files.newBufferedReader(path,java.nio.charset.StandardCharsets.UTF_8)){char[] buffer=new char[4096];WipingChars out=new WipingChars();int count,total=0;try{while((count=reader.read(buffer))>=0){total+=count;if(total>65536)throw new SecurityException("provider secret exceeds limit");out.write(buffer,0,count);}char[] value=out.toCharArray();if(value.length==0)throw new SecurityException("provider secret is empty");return value;}finally{Arrays.fill(buffer,'\0');out.wipe();}}catch(RuntimeException error){throw error;}catch(Exception error){throw new IllegalStateException("provider secret read failed",error);}}
    private static final class WipingChars extends java.io.CharArrayWriter{void wipe(){Arrays.fill(buf,'\0');reset();}}
}
