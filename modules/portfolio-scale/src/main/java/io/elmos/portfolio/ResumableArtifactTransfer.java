package io.elmos.portfolio;

import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.portfolio.PortfolioScaleModels.requireText;

public final class ResumableArtifactTransfer {
    public record RegionRoute(String sourceRegion, String targetRegion) {
        public RegionRoute { requireText(sourceRegion, "source region"); requireText(targetRegion, "target region"); }
    }
    public record TransferManifest(String transferId, String tenantId, String sourceRegion, String targetRegion,
                                   String artifactDigest, long totalBytes, int chunkSize,
                                   List<String> chunkDigests, boolean encrypted) {
        public TransferManifest {
            requireText(transferId, "transfer id"); requireText(tenantId, "transfer tenant");
            requireText(sourceRegion, "source region"); requireText(targetRegion, "target region");
            requireText(artifactDigest, "artifact digest"); chunkDigests = List.copyOf(chunkDigests);
            if (totalBytes < 0 || chunkSize < 1 || chunkDigests.isEmpty() || !encrypted) {
                throw new IllegalArgumentException("invalid or unencrypted transfer manifest");
            }
        }
    }
    private static final class Session {
        private final TransferManifest manifest;
        private final Map<Integer, byte[]> chunks = new HashMap<>();
        private Session(TransferManifest manifest) { this.manifest = manifest; }
    }

    private final Set<RegionRoute> allowedRoutes;
    private final long maximumBytes;
    private final Map<String, Session> sessions = new HashMap<>();

    public ResumableArtifactTransfer(Set<RegionRoute> allowedRoutes, long maximumBytes) {
        this.allowedRoutes = Set.copyOf(allowedRoutes);
        if (maximumBytes < 1) throw new IllegalArgumentException("maximum transfer size must be positive");
        this.maximumBytes = maximumBytes;
    }

    public TransferManifest begin(String transferId, String tenantId, String sourceRegion, String targetRegion,
                                  byte[] artifact, int chunkSize, boolean encrypted) {
        if (chunkSize < 1) throw new IllegalArgumentException("chunk size must be positive");
        if (!allowedRoutes.contains(new RegionRoute(sourceRegion, targetRegion))) throw new SecurityException("regional transfer route is not allowed");
        if (!encrypted) throw new SecurityException("artifact transfer must be encrypted");
        if (artifact.length > maximumBytes) throw new IllegalArgumentException("artifact exceeds transfer budget");
        List<String> digests = new ArrayList<>();
        for (int offset = 0; offset < artifact.length; offset += chunkSize) {
            digests.add(TenantContentAddressedCache.digest(Arrays.copyOfRange(artifact, offset, Math.min(artifact.length, offset + chunkSize))));
        }
        if (digests.isEmpty()) digests.add(TenantContentAddressedCache.digest(new byte[0]));
        TransferManifest manifest = new TransferManifest(transferId, tenantId, sourceRegion, targetRegion,
                TenantContentAddressedCache.digest(artifact), artifact.length, chunkSize, digests, true);
        Session prior = sessions.putIfAbsent(scoped(tenantId, transferId), new Session(manifest));
        if (prior != null && !prior.manifest.equals(manifest)) throw new IllegalStateException("transfer id reused with different manifest");
        return prior == null ? manifest : prior.manifest;
    }

    public void uploadChunk(String tenantId, String transferId, int index, byte[] bytes) {
        Session session = requireSession(tenantId, transferId);
        if (index < 0 || index >= session.manifest.chunkDigests().size()) throw new IllegalArgumentException("chunk index out of bounds");
        String actual = TenantContentAddressedCache.digest(bytes);
        if (!actual.equals(session.manifest.chunkDigests().get(index))) throw new IllegalArgumentException("chunk digest mismatch");
        session.chunks.put(index, Arrays.copyOf(bytes, bytes.length));
    }

    public List<Integer> missingChunks(String tenantId, String transferId) {
        Session session = requireSession(tenantId, transferId); List<Integer> result = new ArrayList<>();
        for (int index = 0; index < session.manifest.chunkDigests().size(); index++) if (!session.chunks.containsKey(index)) result.add(index);
        return result;
    }

    public byte[] complete(String tenantId, String transferId) {
        Session session = requireSession(tenantId, transferId);
        if (!missingChunks(tenantId, transferId).isEmpty()) throw new IllegalStateException("transfer is incomplete");
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        session.chunks.entrySet().stream().sorted(Map.Entry.comparingByKey()).forEach(entry -> output.writeBytes(entry.getValue()));
        byte[] artifact = output.toByteArray();
        if (artifact.length != session.manifest.totalBytes()
                || !TenantContentAddressedCache.digest(artifact).equals(session.manifest.artifactDigest())) {
            throw new IllegalStateException("completed artifact failed integrity verification");
        }
        return artifact;
    }

    private Session requireSession(String tenantId, String transferId) {
        Session session = sessions.get(scoped(tenantId, transferId));
        if (session == null) throw new SecurityException("transfer is absent or belongs to another tenant");
        return session;
    }
    private static String scoped(String tenantId, String transferId) { return tenantId + "\0" + transferId; }
}
