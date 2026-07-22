package io.elmos.portfolio;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;
import java.util.Optional;

import static io.elmos.portfolio.PortfolioScaleModels.requireText;

public final class TenantContentAddressedCache {
    public record InputManifest(String sourceDigest, String dependencyDigest, String toolchainDigest,
                                String profileDigest, String policyDigest, String environmentDigest,
                                String generatorDigest) {
        public InputManifest {
            requireText(sourceDigest, "source digest");
            requireText(dependencyDigest, "dependency digest");
            requireText(toolchainDigest, "toolchain digest");
            requireText(profileDigest, "profile digest");
            requireText(policyDigest, "policy digest");
            requireText(environmentDigest, "environment digest");
            requireText(generatorDigest, "generator digest");
        }
        String canonical() {
            return String.join("\0", sourceDigest, dependencyDigest, toolchainDigest, profileDigest,
                    policyDigest, environmentDigest, generatorDigest);
        }
    }
    public record ArtifactRef(String tenantId, String trustDomain, String cacheKey, String artifactDigest, int sizeBytes) {}

    private final Map<String, byte[]> artifacts = new HashMap<>();

    public ArtifactRef put(String tenantId, String trustDomain, InputManifest manifest, byte[] bytes,
                           String expectedArtifactDigest, boolean signatureVerified) {
        requireText(tenantId, "cache tenant");
        requireText(trustDomain, "cache trust domain");
        if (!signatureVerified) throw new IllegalArgumentException("artifact signature is not verified");
        String artifactDigest = digest(bytes);
        if (!artifactDigest.equals(expectedArtifactDigest)) throw new IllegalArgumentException("artifact digest mismatch");
        String cacheKey = digest((tenantId + "\0" + trustDomain + "\0" + manifest.canonical()).getBytes(StandardCharsets.UTF_8));
        artifacts.put(storageKey(tenantId, trustDomain, cacheKey), Arrays.copyOf(bytes, bytes.length));
        return new ArtifactRef(tenantId, trustDomain, cacheKey, artifactDigest, bytes.length);
    }

    public Optional<byte[]> get(String tenantId, String trustDomain, ArtifactRef ref) {
        if (!ref.tenantId().equals(tenantId) || !ref.trustDomain().equals(trustDomain)) return Optional.empty();
        byte[] bytes = artifacts.get(storageKey(tenantId, trustDomain, ref.cacheKey()));
        if (bytes == null) return Optional.empty();
        if (!digest(bytes).equals(ref.artifactDigest())) throw new IllegalStateException("cached artifact corruption detected");
        return Optional.of(Arrays.copyOf(bytes, bytes.length));
    }

    public static String digest(byte[] bytes) {
        try {
            return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private static String storageKey(String tenant, String trust, String cacheKey) {
        return tenant + "\0" + trust + "\0" + cacheKey;
    }
}
