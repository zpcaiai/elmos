package io.elmos.liveworkbench;

import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

import static io.elmos.liveworkbench.LwContracts.*;

/** In-memory adapter used by the core; production hosts replace this through the same immutable contract. */
public final class ImmutableSourceRepository {
    private final Map<String, byte[]> blobs = new HashMap<>();

    public synchronized SourceAnchor store(String tenantId, String repositoryId, String snapshotId, String path,
                                           String symbolId, String source, int byteStart, int byteEnd) {
        byte[] bytes = source.getBytes(StandardCharsets.UTF_8);
        if (byteEnd > bytes.length) throw new IllegalArgumentException("anchor exceeds immutable blob");
        SourceAnchor anchor = new SourceAnchor(tenantId, repositoryId, snapshotId, path, LwDigest.sha256(bytes), byteStart, byteEnd,
                "utf8-byte-half-open", symbolId);
        blobs.put(key(anchor), bytes.clone());
        return anchor;
    }

    public synchronized String resolve(Authority authority, SourceAnchor anchor, long now) {
        requireAuthority(authority, anchor, now, Capability.INSPECT);
        byte[] blob = blobs.get(key(anchor));
        if (blob == null || !LwDigest.sha256(blob).equals(anchor.blobDigest())) throw new IllegalStateException("immutable source blob unavailable");
        if (anchor.byteEnd() > blob.length) throw new IllegalStateException("anchor became invalid");
        return new String(blob, anchor.byteStart(), anchor.byteEnd() - anchor.byteStart(), StandardCharsets.UTF_8);
    }

    private static String key(SourceAnchor anchor) { return anchor.tenantId()+"|"+anchor.repositoryId()+"|"+anchor.snapshotId()+"|"+anchor.path(); }
    static void requireAuthority(Authority authority, SourceAnchor anchor, long now, Capability capability) {
        if (authority == null || !authority.validAt(now, capability)) throw new SecurityException("authority expired or capability denied");
        Binding binding = authority.binding();
        if (!binding.tenantId().equals(anchor.tenantId()) || !binding.repositoryId().equals(anchor.repositoryId()) || !binding.snapshotId().equals(anchor.snapshotId()))
            throw new SecurityException("cross-scope source access denied");
    }
}
