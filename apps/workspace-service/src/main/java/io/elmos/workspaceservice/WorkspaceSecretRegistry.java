package io.elmos.workspaceservice;

import io.elmos.workspace.WorkspaceInfrastructurePorts;

import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

final class WorkspaceSecretRegistry implements WorkspaceInfrastructurePorts.CommandOutputSanitizer {
    private static final byte[] REDACTED="[REDACTED]".getBytes(StandardCharsets.UTF_8);
    private final Map<String,Map<String,byte[]>> active=new ConcurrentHashMap<>();
    void register(String workspaceId,String leaseId,char[] value){java.nio.ByteBuffer encoded=StandardCharsets.UTF_8.encode(java.nio.CharBuffer.wrap(value));byte[] bytes=new byte[encoded.remaining()];encoded.get(bytes);if(bytes.length<4)throw new SecurityException("secret is too short for reliable redaction");active.computeIfAbsent(workspaceId,ignored->new ConcurrentHashMap<>()).put(leaseId,bytes);}
    void remove(String workspaceId,String leaseId){Map<String,byte[]> values=active.get(workspaceId);if(values==null)return;byte[] removed=values.remove(leaseId);if(removed!=null)Arrays.fill(removed,(byte)0);if(values.isEmpty())active.remove(workspaceId,values);}
    void clear(String workspaceId){Map<String,byte[]> values=active.remove(workspaceId);if(values!=null)values.values().forEach(value->Arrays.fill(value,(byte)0));}
    @Override public byte[] sanitize(String workspaceId,byte[] raw){byte[] result=raw.clone();Map<String,byte[]> secrets=active.getOrDefault(workspaceId,Map.of());for(byte[] secret:secrets.values())result=replace(result,secret,REDACTED);return result;}
    private static byte[] replace(byte[] source,byte[] pattern,byte[] replacement){java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();for(int i=0;i<source.length;){boolean match=i+pattern.length<=source.length;for(int j=0;match&&j<pattern.length;j++)match=source[i+j]==pattern[j];if(match){out.writeBytes(replacement);i+=pattern.length;}else out.write(source[i++]);}return out.toByteArray();}
}
