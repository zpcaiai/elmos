package io.elmos.cas;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/**
 * Heap implementation of {@link CasCatalog}, enforcing the same invariants the V65/V66 schema does.
 *
 * <p>It is the reference the JDBC implementation is checked against, and it is what a single
 * process deployment or a test uses. Where the schema has a constraint, this class throws — the
 * two must agree, because a rule that only the database enforces is a rule the in-memory path
 * silently violates until the first integration test.
 */
public final class InMemoryCasCatalog implements CasCatalog {

    private final Map<String, CatalogEntry> entries = new LinkedHashMap<>();
    private final Map<BindingKey, ResourceBinding> resourceBindings = new LinkedHashMap<>();
    private final Map<BindingKey, Long> releasedResourceBindings = new LinkedHashMap<>();
    private final Map<String, List<Placement>> placements = new LinkedHashMap<>();
    private final Map<RootObjectKey, ReferenceRoot> roots = new LinkedHashMap<>();
    private final Map<RootObjectKey, Long> releasedRoots = new LinkedHashMap<>();
    private final Map<String, String> deletionBatches = new LinkedHashMap<>();
    private final Map<String, String> quarantines = new LinkedHashMap<>();

    private static String key(String tenantId, CasDigest digest) {
        return tenantId + '\0' + digest.hex();
    }

    private record RootObjectKey(String tenantId, CasGarbageCollector.RootKind kind, String rootId,
                                 String digestHex) {
    }

    private static RootObjectKey rootKey(ReferenceRoot root) {
        return new RootObjectKey(root.tenantId(), root.kind(), root.rootId(), root.digest().hex());
    }

    private record BindingKey(String tenantId, ResourceKind resourceKind, String resourceId,
                              String digestHex) {
    }

    private static BindingKey resourceKey(String tenantId, ResourceKind resourceKind, String resourceId,
                                          CasDigest digest) {
        return new BindingKey(tenantId, resourceKind, resourceId, digest.hex());
    }

    @Override
    public synchronized void record(CatalogEntry entry) {
        String key = key(entry.tenantId(), entry.digest());
        CatalogEntry existing = entries.get(key);
        if (existing == null) {
            entries.put(key, entry);
            return;
        }
        if (!sameImmutableIdentity(existing, entry)) {
            throw new IllegalStateException(
                    "catalogued object identity cannot be rebound to different metadata");
        }
        // Mirrors JdbcCasCatalog: only lifecycle fields are refreshed by an idempotent record.
        entries.put(key, new CatalogEntry(existing.tenantId(), existing.digest(),
                existing.kind(), existing.mediaType(), existing.sourceSystem(),
                existing.schemaVersion(), existing.sensitivity(),
                strongerRetention(existing.retentionClass(), entry.retentionClass()),
                existing.dataResidency(), existing.securityTier(), existing.provenanceDigest(),
                mergeLabels(existing.labels(), entry.labels()),
                existing.legalHold() || entry.legalHold(),
                existing.createdAtEpochMillis()));
    }

    @Override
    public synchronized Optional<CatalogEntry> find(String tenantId, CasDigest digest) {
        CasText.required(tenantId, "tenantId");
        Objects.requireNonNull(digest, "digest");
        CatalogEntry entry = entries.get(key(tenantId, digest));
        return entry != null && entry.digest().equals(digest) ? Optional.of(entry) : Optional.empty();
    }

    @Override
    public synchronized Optional<CatalogEntry> findBound(
            String tenantId,
            ResourceKind resourceKind,
            String resourceId,
            CasDigest digest) {
        requireResourceLookup(tenantId, resourceKind, resourceId, digest);
        BindingKey bindingKey = resourceKey(tenantId, resourceKind, resourceId, digest);
        if (!resourceBindings.containsKey(bindingKey)
                || releasedResourceBindings.containsKey(bindingKey)) {
            return Optional.empty();
        }
        return find(tenantId, digest);
    }

    @Override
    public synchronized void bindResource(ResourceBinding binding) {
        if (find(binding.tenantId(), binding.digest()).isEmpty()) {
            throw new CasExceptions.CasNotFoundException(binding.digest());
        }
        BindingKey bindingKey = resourceKey(binding.tenantId(), binding.resourceKind(),
                binding.resourceId(), binding.digest());
        if (!resourceBindings.containsKey(bindingKey)
                || releasedResourceBindings.containsKey(bindingKey)) {
            resourceBindings.put(bindingKey, binding);
        }
        releasedResourceBindings.remove(bindingKey);
    }

    @Override
    public synchronized void releaseResource(
            String tenantId,
            ResourceKind resourceKind,
            String resourceId,
            CasDigest digest,
            long releasedAtEpochMillis) {
        requireResourceLookup(tenantId, resourceKind, resourceId, digest);
        if (releasedAtEpochMillis < 0) {
            throw new IllegalArgumentException("releasedAtEpochMillis must not be negative");
        }
        BindingKey bindingKey = resourceKey(tenantId, resourceKind, resourceId, digest);
        ResourceBinding binding = resourceBindings.get(bindingKey);
        if (binding != null) {
            if (releasedAtEpochMillis < binding.boundAtEpochMillis()) {
                throw new IllegalArgumentException("release cannot precede resource binding");
            }
            releasedResourceBindings.putIfAbsent(bindingKey, releasedAtEpochMillis);
        }
    }

    @Override
    public synchronized List<ResourceBinding> activeResourceBindings(
            String tenantId,
            ResourceKind resourceKind,
            String resourceId) {
        CasText.required(tenantId, "tenantId");
        Objects.requireNonNull(resourceKind, "resourceKind");
        CasText.required(resourceId, "resourceId");
        return resourceBindings.entrySet().stream()
                .filter(entry -> entry.getKey().tenantId().equals(tenantId))
                .filter(entry -> entry.getKey().resourceKind() == resourceKind)
                .filter(entry -> entry.getKey().resourceId().equals(resourceId))
                .filter(entry -> !releasedResourceBindings.containsKey(entry.getKey()))
                .map(Map.Entry::getValue)
                .toList();
    }

    @Override
    public synchronized Map<CasDigest, CasObjectModel.ObjectMetadata> load(
            String tenantId, Set<CasDigest> digests) {
        Map<CasDigest, CasObjectModel.ObjectMetadata> loaded = new LinkedHashMap<>();
        for (CasDigest digest : digests) {
            find(tenantId, digest).ifPresent(entry -> loaded.put(digest, entry.metadata()));
        }
        return Collections.unmodifiableMap(loaded);
    }

    @Override
    public synchronized void placeObject(Placement placement) {
        if (find(placement.tenantId(), placement.digest()).isEmpty()) {
            // Mirrors the foreign key: a placement for an object nobody catalogued is a row that
            // the collector can never reason about.
            throw new IllegalStateException("cannot place an uncatalogued object: " + placement.digest());
        }
        List<Placement> existing = placements.computeIfAbsent(
                key(placement.tenantId(), placement.digest()), ignored -> new ArrayList<>());
        if (placement.role() == PlacementRole.PRIMARY
                && existing.stream().anyMatch(entry -> entry.role() == PlacementRole.PRIMARY
                        && !entry.region().equals(placement.region()))) {
            throw new IllegalStateException("object already has a primary region");
        }
        existing.removeIf(entry -> entry.region().equals(placement.region()));
        existing.add(placement);
    }

    @Override
    public synchronized List<Placement> placements(String tenantId, CasDigest digest) {
        if (find(tenantId, digest).isEmpty()) {
            return List.of();
        }
        return List.copyOf(placements.getOrDefault(key(tenantId, digest), List.of()));
    }

    @Override
    public synchronized void addReferenceRoot(ReferenceRoot root) {
        addReferenceRoots(List.of(root));
    }

    @Override
    public synchronized long addReferenceRoots(List<ReferenceRoot> requestedRoots) {
        ReferenceRoot first = requireOneRootSet(requestedRoots);
        Map<String, ReferenceRoot> requestedByHex = new LinkedHashMap<>();
        for (ReferenceRoot root : requestedRoots) {
            ReferenceRoot duplicate = requestedByHex.putIfAbsent(root.digest().hex(), root);
            if (duplicate != null && !duplicate.digest().equals(root.digest())) {
                throw new IllegalArgumentException("one digest hex cannot carry two sizes in a root set");
            }
        }
        boolean hasHistory = false;
        boolean hasActive = false;
        long historicalGeneration = -1;
        long activeGeneration = -1;
        for (Map.Entry<RootObjectKey, ReferenceRoot> existing : roots.entrySet()) {
            RootObjectKey key = existing.getKey();
            if (sameRootIdentity(key, first)) {
                hasHistory = true;
                historicalGeneration = Math.max(
                        historicalGeneration, existing.getValue().createdAtEpochMillis());
                if (!releasedRoots.containsKey(key)) {
                    long generation = existing.getValue().createdAtEpochMillis();
                    if (hasActive && activeGeneration != generation) {
                        throw new IllegalStateException(
                                "active reference root spans multiple generations");
                    }
                    hasActive = true;
                    activeGeneration = generation;
                }
                ReferenceRoot requested = requestedByHex.get(key.digestHex());
                if (requested != null && !requested.digest().equals(existing.getValue().digest())) {
                    throw new IllegalStateException("reference root digest size conflicts with history");
                }
                if (!releasedRoots.containsKey(key) && requested == null) {
                    throw new IllegalStateException("active reference root conflicts with requested digest set");
                }
            }
        }
        long requestedGeneration = requestedByHex.values().stream()
                .mapToLong(ReferenceRoot::createdAtEpochMillis)
                .max().orElseThrow();
        long publicationGeneration = requestedGeneration;
        if (hasActive) {
            publicationGeneration = activeGeneration;
        } else if (hasHistory) {
            publicationGeneration = Math.max(
                    requestedGeneration, Math.addExact(historicalGeneration, 1L));
        }
        for (ReferenceRoot requested : requestedByHex.values()) {
            ReferenceRoot root = hasActive || hasHistory
                    ? new ReferenceRoot(requested.tenantId(), requested.kind(),
                    requested.rootId(), requested.digest(), publicationGeneration)
                    : requested;
            RootObjectKey key = rootKey(root);
            if (!roots.containsKey(key) || releasedRoots.containsKey(key)) {
                // A reactivated logical root is a new lifecycle generation. Keeping the original
                // creation time would let a delayed release from the old generation hide it.
                roots.put(key, root);
            }
            releasedRoots.remove(key);
        }
        return roots.entrySet().stream()
                .filter(entry -> sameRootIdentity(entry.getKey(), first))
                .filter(entry -> !releasedRoots.containsKey(entry.getKey()))
                .mapToLong(entry -> entry.getValue().createdAtEpochMillis())
                .max().orElseThrow(() -> new IllegalStateException(
                        "reference root publication produced no active generation"));
    }

    @Override
    public synchronized void releaseReferenceRoot(
            String tenantId,
            CasGarbageCollector.RootKind kind,
            String rootId,
            long releasedAtEpochMillis) {
        CasText.required(tenantId, "tenantId");
        Objects.requireNonNull(kind, "kind");
        CasText.required(rootId, "rootId");
        if (releasedAtEpochMillis < 0) {
            throw new IllegalArgumentException("releasedAtEpochMillis must not be negative");
        }
        List<RootObjectKey> matching = roots.keySet().stream()
                .filter(key -> key.tenantId().equals(tenantId))
                .filter(key -> key.kind() == kind)
                .filter(key -> key.rootId().equals(rootId))
                .filter(key -> !releasedRoots.containsKey(key))
                .toList();
        if (matching.stream().map(roots::get)
                .anyMatch(root -> root.createdAtEpochMillis() > releasedAtEpochMillis)) {
            throw new IllegalArgumentException("release cannot precede reference root creation");
        }
        matching.forEach(key -> releasedRoots.put(key, releasedAtEpochMillis));
    }

    @Override
    public synchronized List<ReferenceRoot> activeReferenceRoots(String tenantId) {
        List<ReferenceRoot> active = new ArrayList<>();
        roots.forEach((key, root) -> {
            if (root.tenantId().equals(tenantId) && !releasedRoots.containsKey(key)) {
                active.add(root);
            }
        });
        return List.copyOf(active);
    }

    @Override
    public synchronized void setLegalHold(String tenantId, CasDigest digest, boolean legalHold) {
        CatalogEntry entry = find(tenantId, digest)
                .orElseThrow(() -> new CasExceptions.CasNotFoundException(digest));
        entries.put(key(tenantId, digest), new CatalogEntry(entry.tenantId(), entry.digest(),
                entry.kind(), entry.mediaType(), entry.sourceSystem(),
                entry.schemaVersion(), entry.sensitivity(), entry.retentionClass(), entry.dataResidency(),
                entry.securityTier(), entry.provenanceDigest(), entry.labels(), legalHold,
                entry.createdAtEpochMillis()));
    }

    @Override
    public synchronized void recordDeletionManifest(
            String tenantId,
            CasGarbageCollector.DeletionManifest manifest,
            String executedBy) {
        String batchKey = tenantId + '\0' + manifest.batchId();
        if (deletionBatches.containsKey(batchKey)) {
            throw new IllegalStateException("append-only: deletion batch already recorded: " + manifest.batchId());
        }
        deletionBatches.put(batchKey, manifest.digest().hex() + '/' + executedBy);
    }

    @Override
    public synchronized List<String> deletionBatchIds(String tenantId) {
        return deletionBatches.keySet().stream()
                .filter(key -> key.startsWith(tenantId + '\0'))
                .map(key -> key.substring(tenantId.length() + 1))
                .toList();
    }

    @Override
    public synchronized void recordQuarantine(
            String tenantId,
            String quarantineId,
            String subjectKind,
            String subject,
            Optional<CasDigest> declared,
            Optional<CasDigest> observed,
            String detail,
            long detectedAtEpochMillis) {
        if (!"NODE".equals(subjectKind) && (declared.isEmpty() || observed.isEmpty())) {
            throw new IllegalArgumentException("a content quarantine needs both the declared and the "
                    + "observed digest or it cannot be investigated");
        }
        String quarantineKey = tenantId + '\0' + quarantineId;
        if (quarantines.putIfAbsent(quarantineKey, subjectKind + '/' + subject + '/' + detail) != null) {
            throw new IllegalStateException("append-only: quarantine already recorded: " + quarantineId);
        }
    }

    @Override
    public synchronized int quarantineCount(String tenantId) {
        return (int) quarantines.keySet().stream().filter(key -> key.startsWith(tenantId + '\0')).count();
    }

    private static boolean sameImmutableIdentity(CatalogEntry left, CatalogEntry right) {
        return left.tenantId().equals(right.tenantId())
                && left.digest().equals(right.digest())
                && left.kind() == right.kind()
                && left.mediaType().equals(right.mediaType())
                && left.sourceSystem().equals(right.sourceSystem())
                && left.schemaVersion().equals(right.schemaVersion())
                && left.sensitivity() == right.sensitivity()
                && left.dataResidency().equals(right.dataResidency())
                && left.securityTier() == right.securityTier()
                && left.provenanceDigest().equals(right.provenanceDigest());
    }

    private static CasObjectModel.RetentionClass strongerRetention(
            CasObjectModel.RetentionClass left,
            CasObjectModel.RetentionClass right) {
        if (left == CasObjectModel.RetentionClass.REGULATORY
                || right == CasObjectModel.RetentionClass.REGULATORY) {
            return CasObjectModel.RetentionClass.REGULATORY;
        }
        if (left == CasObjectModel.RetentionClass.EVIDENCE
                || right == CasObjectModel.RetentionClass.EVIDENCE) {
            return CasObjectModel.RetentionClass.EVIDENCE;
        }
        if (left == CasObjectModel.RetentionClass.STANDARD
                || right == CasObjectModel.RetentionClass.STANDARD) {
            return CasObjectModel.RetentionClass.STANDARD;
        }
        return CasObjectModel.RetentionClass.EPHEMERAL;
    }

    private static Map<String, String> mergeLabels(Map<String, String> existing,
                                                    Map<String, String> update) {
        Map<String, String> merged = new LinkedHashMap<>(existing);
        merged.putAll(update);
        return Map.copyOf(merged);
    }

    private static ReferenceRoot requireOneRootSet(List<ReferenceRoot> requestedRoots) {
        if (requestedRoots == null || requestedRoots.isEmpty()) {
            throw new IllegalArgumentException("reference root batch must not be empty");
        }
        ReferenceRoot first = Objects.requireNonNull(requestedRoots.get(0), "reference root");
        for (ReferenceRoot root : requestedRoots) {
            Objects.requireNonNull(root, "reference root");
            if (!root.tenantId().equals(first.tenantId())
                    || root.kind() != first.kind()
                    || !root.rootId().equals(first.rootId())) {
                throw new IllegalArgumentException(
                        "reference root batch must share tenant, kind, and root ID");
            }
        }
        return first;
    }

    private static boolean sameRootIdentity(RootObjectKey key, ReferenceRoot root) {
        return key.tenantId().equals(root.tenantId())
                && key.kind() == root.kind()
                && key.rootId().equals(root.rootId());
    }

    private static void requireResourceLookup(String tenantId, ResourceKind resourceKind,
                                              String resourceId, CasDigest digest) {
        CasText.required(tenantId, "tenantId");
        Objects.requireNonNull(resourceKind, "resourceKind");
        CasText.required(resourceId, "resourceId");
        Objects.requireNonNull(digest, "digest");
    }
}
