package io.elmos.portfolio;

import io.elmos.cas.CasDigest;
import io.elmos.cas.CasExceptions;
import io.elmos.cas.CasStore;
import io.elmos.cas.InMemoryCasStore;
import io.elmos.cas.TieredCasStore;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import static io.elmos.portfolio.PortfolioScaleModels.requireText;

/**
 * Portfolio-facing view of the content-addressed cache.
 *
 * <p>This used to be a {@code HashMap<String, byte[]>} with a cache key built by
 * {@code String.join("\0", ...)}. It now delegates to {@code modules/cas}, which changes three
 * things that mattered:
 *
 * <ul>
 *   <li><b>The key is length-prefixed.</b> Joining seven attacker-influenceable digests with a
 *       separator lets any one of them spell that separator and collapse two different input sets
 *       onto one key.</li>
 *   <li><b>Storage verifies on read.</b> The old class recomputed the digest in {@code get} but
 *       kept the poisoned bytes; the store quarantines them and refuses to serve them again.</li>
 *   <li><b>The object tier is replaceable.</b> A {@link TieredCasStore} can share immutable
 *       artifact bytes, but this adapter's key-to-digest index is deliberately process-local.
 *       Cross-instance hits require a durable tenant-scoped index; changing only the object
 *       store does not provide them.</li>
 * </ul>
 *
 * <p>The public shape is unchanged so existing callers and tests keep working.
 */
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

        List<String> fields() {
            return List.of(sourceDigest, dependencyDigest, toolchainDigest, profileDigest,
                    policyDigest, environmentDigest, generatorDigest);
        }
    }

    public record ArtifactRef(String tenantId, String trustDomain, String cacheKey, String artifactDigest,
                              int sizeBytes) {
    }

    private final CasStore store;
    /** cache key -> the content digest it resolves to, per tenant and trust domain. */
    private final Map<String, CasDigest> index = new ConcurrentHashMap<>();

    public TenantContentAddressedCache() {
        this(new InMemoryCasStore("portfolio-cache"));
    }

    public TenantContentAddressedCache(CasStore store) {
        this.store = store;
    }

    public ArtifactRef put(String tenantId, String trustDomain, InputManifest manifest, byte[] bytes,
                           String expectedArtifactDigest, boolean signatureVerified) {
        requireText(tenantId, "cache tenant");
        requireText(trustDomain, "cache trust domain");
        if (!signatureVerified) {
            throw new IllegalArgumentException("artifact signature is not verified");
        }
        CasDigest artifact = CasDigest.of(bytes);
        if (!digest(bytes).equals(expectedArtifactDigest)) {
            throw new IllegalArgumentException("artifact digest mismatch");
        }
        store.put(artifact, bytes);
        String cacheKey = cacheKey(tenantId, trustDomain, manifest);
        index.put(storageKey(tenantId, trustDomain, cacheKey), artifact);
        return new ArtifactRef(tenantId, trustDomain, cacheKey, digest(bytes), bytes.length);
    }

    public Optional<byte[]> get(String tenantId, String trustDomain, ArtifactRef ref) {
        if (!ref.tenantId().equals(tenantId) || !ref.trustDomain().equals(trustDomain)) {
            return Optional.empty();
        }
        CasDigest artifact = index.get(storageKey(tenantId, trustDomain, ref.cacheKey()));
        if (artifact == null) {
            return Optional.empty();
        }
        if (!digest(artifact).equals(ref.artifactDigest())) {
            throw new IllegalStateException("cached artifact identity does not match the reference");
        }
        try {
            return Optional.of(store.get(artifact));
        } catch (CasExceptions.CasNotFoundException collected) {
            index.remove(storageKey(tenantId, trustDomain, ref.cacheKey()));
            return Optional.empty();
        } catch (CasExceptions.CasCorruptionException poisoned) {
            // The store has already quarantined the bytes. Surfacing it keeps the historical
            // contract of this class, which callers treat as an unrecoverable cache fault.
            throw new IllegalStateException("cached artifact corruption detected", poisoned);
        }
    }

    /** Kept for source compatibility: callers pass the result straight back into {@link #put}. */
    public static String digest(byte[] bytes) {
        return "sha256:" + CasDigest.of(bytes).hex();
    }

    private static String digest(CasDigest digest) {
        return "sha256:" + digest.hex();
    }

    /**
     * Length-prefixed so no field can impersonate a separator. Two input sets that differ produce
     * two keys, whatever characters the digests contain.
     */
    private static String cacheKey(String tenantId, String trustDomain, InputManifest manifest) {
        StringBuilder canonical = new StringBuilder("elmos-portfolio-cache-key/1\n");
        for (String field : concat(tenantId, trustDomain, manifest.fields())) {
            byte[] encoded = field.getBytes(StandardCharsets.UTF_8);
            canonical.append(encoded.length).append(':').append(field).append('\n');
        }
        return CasDigest.ofUtf8(canonical.toString()).hex();
    }

    private static List<String> concat(String tenantId, String trustDomain, List<String> fields) {
        String[] all = new String[fields.size() + 2];
        all[0] = tenantId;
        all[1] = trustDomain;
        for (int index = 0; index < fields.size(); index++) {
            all[index + 2] = fields.get(index);
        }
        return Arrays.asList(all);
    }

    private static String storageKey(String tenant, String trust, String cacheKey) {
        return tenant + '\0' + trust + '\0' + cacheKey;
    }
}
