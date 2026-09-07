package io.elmos.semantic;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class SemanticIds {
    private SemanticIds() {}
    public static String file(String snapshotId, String path) { return id("file", snapshotId, path); }
    public static String node(String snapshotId, String path, String parser, String kind, long start, long end) { return id("node", snapshotId, path, parser, kind, start, end); }
    public static String symbol(String language, String project, String canonicalKey) { return id("sym", language, project, canonicalKey); }
    public static String local(String fileId, String scopeId, String kind, long start) { return id("sym", fileId, scopeId, kind, start); }
    public static String unresolved(String language, String fileId, String name, long start) { return id("sym-unresolved", language, fileId, name, start); }
    public static String type(String language, String canonical) { return id("type", language, canonical); }
    public static String scope(String fileId, String kind, long start) { return id("scope", fileId, kind, start); }
    public static String edge(String kind, String source, String target, String node) { return id("edge", kind, source, target, node); }
    public static String call(String fileId, long start, long end) { return id("call", fileId, start, end); }
    public static String diagnostic(String provider, String category, String fileId, long start, String code) { return id("diag", provider, category, fileId, start, code); }
    public static String cacheKey(String snapshotId, String fileHash, String adapterVersion, String compilerOptionsHash,
                                  String dependencyGraphHash, String protocolVersion) {
        return "sha256:" + hash(join(snapshotId, fileHash, adapterVersion, compilerOptionsHash, dependencyGraphHash, protocolVersion));
    }
    public static String id(String prefix, Object... parts) { return prefix + ":" + hash(join(parts)); }
    public static String hashText(String value) { return "sha256:" + hash(value.getBytes(StandardCharsets.UTF_8)); }
    private static byte[] join(Object... parts) { StringBuilder value = new StringBuilder(); for (Object part : parts) value.append(part == null ? "<null>" : part).append('\0'); return value.toString().getBytes(StandardCharsets.UTF_8); }
    private static String hash(byte[] bytes) { try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); } catch (Exception error) { throw new IllegalStateException(error); } }
}
