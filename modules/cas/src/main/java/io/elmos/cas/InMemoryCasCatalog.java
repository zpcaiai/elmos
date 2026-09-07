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
    private final Map<RootObjectKey, ResourceLifecycle> rootResources = new LinkedHashMap<>();
    private final Map<String, TenantLifecycle> tenantLifecycles = new LinkedHashMap<>();
    private final Map<ResourceKey, ResourceLifecycle> resourceLifecycles = new LinkedHashMap<>();
    private final Map<String, String> deletionTombstones = new LinkedHashMap<>();
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

    private record ResourceKey(String tenantId, ResourceKind resourceKind, String resourceId) {
    }

    private record TenantLifecycle(long epoch, ResourceLifecycleState state,
                                   long transitionedAtEpochMillis) {
    }

    private static BindingKey resourceKey(String tenantId, ResourceKind resourceKind, String resourceId,
                                          CasDigest digest) {
        return new BindingKey(tenantId, resourceKind, resourceId, digest.hex());
    }

    private static ResourceKey resourceKey(ResourceLifecycle resource) {
        return new ResourceKey(resource.tenantId(), resource.resourceKind(), resource.resourceId());
    }

    @Override
    public synchronized void record(CatalogEntry entry) {
        requireTenantActive(entry.tenantId());
        String key = key(entry.tenantId(), entry.digest());
        if (entry.legalHold() && deletionTombstones.containsKey(key)) {
            throw new IllegalStateException(
                    "a legal hold cannot be attached while object deletion is unresolved");
        }
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
    public synchronized long recordAndAddReferenceRoots(
            CatalogEntry entry, List<ReferenceRoot> requestedRoots
    ) {
        ReferenceRoot first = requireOneRootSet(requestedRoots);
        if (!entry.tenantId().equals(first.tenantId())
                || requestedRoots.stream().noneMatch(root -> root.digest().equals(entry.digest()))) {
            throw new IllegalArgumentException(
                    "catalogue entry and root set must share tenant and contain the object");
        }
        Map<String, CatalogEntry> priorEntries = new LinkedHashMap<>(entries);
        Map<RootObjectKey, ReferenceRoot> priorRoots = new LinkedHashMap<>(roots);
        Map<RootObjectKey, Long> priorReleasedRoots = new LinkedHashMap<>(releasedRoots);
        try {
            record(entry);
            return addReferenceRoots(requestedRoots);
        } catch (RuntimeException | Error failure) {
            entries.clear();
            entries.putAll(priorEntries);
            roots.clear();
            roots.putAll(priorRoots);
            releasedRoots.clear();
            releasedRoots.putAll(priorReleasedRoots);
            throw failure;
        }
    }

    @Override
    public synchronized long recordAndPublishDurableReferenceRoots(
            CatalogEntry entry,
            List<ReferenceRoot> requestedRoots,
            DurableObjectEnsurer durableObjectEnsurer
    ) {
        ReferenceRoot first = requireOneRootSet(requestedRoots);
        Objects.requireNonNull(durableObjectEnsurer, "durableObjectEnsurer");
        if (!entry.tenantId().equals(first.tenantId())
                || requestedRoots.stream().noneMatch(root -> root.digest().equals(entry.digest()))) {
            throw new IllegalArgumentException(
                    "catalogue entry and root set must share tenant and contain the object");
        }
        Map<String, CatalogEntry> priorEntries = new LinkedHashMap<>(entries);
        Map<RootObjectKey, ReferenceRoot> priorRoots = new LinkedHashMap<>(roots);
        Map<RootObjectKey, Long> priorReleasedRoots = new LinkedHashMap<>(releasedRoots);
        Map<String, String> priorTombstones = new LinkedHashMap<>(deletionTombstones);
        try {
            ensureNoActiveDeletionTombstones(first.tenantId(), requestedRoots.stream()
                    .map(ReferenceRoot::digest).toList());
            durableObjectEnsurer.ensureDurable();
            clearRepairableDeletionTombstones(first.tenantId(), requestedRoots.stream()
                    .map(ReferenceRoot::digest).toList());
            record(entry);
            return addReferenceRoots(requestedRoots);
        } catch (RuntimeException | Error failure) {
            entries.clear();
            entries.putAll(priorEntries);
            roots.clear();
            roots.putAll(priorRoots);
            releasedRoots.clear();
            releasedRoots.putAll(priorReleasedRoots);
            deletionTombstones.clear();
            deletionTombstones.putAll(priorTombstones);
            throw failure;
        }
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
        ResourceLifecycle resource = ensureActiveResource(
                binding.tenantId(), binding.resourceKind(), binding.resourceId());
        bindResource(binding, resource);
    }

    private void bindResource(ResourceBinding binding, ResourceLifecycle resource) {
        requireExactActiveResource(resource);
        if (deletionTombstones.containsKey(key(binding.tenantId(), binding.digest()))) {
            throw new IllegalStateException(
                    "resource binding is blocked by an unresolved deletion");
        }
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
    public synchronized void recordAndBindDurableResource(
            CatalogEntry entry,
            ResourceBinding binding,
            DurableObjectEnsurer durableObjectEnsurer
    ) {
        ResourceLifecycle resource = ensureActiveResource(
                binding.tenantId(), binding.resourceKind(), binding.resourceId());
        recordAndBindDurableResource(entry, binding, resource, durableObjectEnsurer);
    }

    @Override
    public synchronized void recordAndBindDurableResource(
            CatalogEntry entry,
            ResourceBinding binding,
            ResourceLifecycle resource,
            DurableObjectEnsurer durableObjectEnsurer
    ) {
        Objects.requireNonNull(entry, "entry");
        Objects.requireNonNull(binding, "binding");
        Objects.requireNonNull(resource, "resource");
        Objects.requireNonNull(durableObjectEnsurer, "durableObjectEnsurer");
        if (!entry.tenantId().equals(binding.tenantId())
                || !entry.digest().equals(binding.digest())) {
            throw new IllegalArgumentException(
                    "catalogue entry and resource binding must identify the same tenant object");
        }
        Map<String, CatalogEntry> priorEntries = new LinkedHashMap<>(entries);
        Map<BindingKey, ResourceBinding> priorBindings =
                new LinkedHashMap<>(resourceBindings);
        Map<BindingKey, Long> priorReleasedBindings =
                new LinkedHashMap<>(releasedResourceBindings);
        Map<String, String> priorTombstones = new LinkedHashMap<>(deletionTombstones);
        try {
            requireExactActiveResource(resource);
            requireBindingResource(binding, resource);
            ensureNoActiveDeletionTombstones(
                    entry.tenantId(), List.of(entry.digest()));
            durableObjectEnsurer.ensureDurable();
            clearRepairableDeletionTombstones(
                    entry.tenantId(), List.of(entry.digest()));
            record(entry);
            bindResource(binding, resource);
        } catch (RuntimeException | Error failure) {
            entries.clear();
            entries.putAll(priorEntries);
            resourceBindings.clear();
            resourceBindings.putAll(priorBindings);
            releasedResourceBindings.clear();
            releasedResourceBindings.putAll(priorReleasedBindings);
            deletionTombstones.clear();
            deletionTombstones.putAll(priorTombstones);
            throw failure;
        }
    }

    @Override
    public synchronized ResourceLifecycle ensureActiveResource(
            String tenantId, ResourceKind resourceKind, String resourceId) {
        CasText.required(tenantId, "tenantId");
        Objects.requireNonNull(resourceKind, "resourceKind");
        CasText.required(resourceId, "resourceId");
        TenantLifecycle tenant = tenantLifecycles.computeIfAbsent(
                tenantId, ignored -> new TenantLifecycle(
                        1, ResourceLifecycleState.ACTIVE, 0));
        if (tenant.state() != ResourceLifecycleState.ACTIVE) {
            throw new IllegalStateException("CAS tenant is not ACTIVE");
        }
        ResourceKey key = new ResourceKey(tenantId, resourceKind, resourceId);
        ResourceLifecycle current = resourceLifecycles.computeIfAbsent(key,
                ignored -> new ResourceLifecycle(tenantId, resourceKind, resourceId,
                        tenant.epoch(), 1, ResourceLifecycleState.ACTIVE, 0, 0));
        requireExactActiveResource(current);
        return current;
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
        return addReferenceRoots(requestedRoots, false);
    }

    private long addReferenceRoots(
            List<ReferenceRoot> requestedRoots, boolean resourcePublication) {
        ReferenceRoot first = requireOneRootSet(requestedRoots);
        requireTenantActive(first.tenantId());
        if (!resourcePublication && requestedRoots.stream()
                .map(InMemoryCasCatalog::rootKey)
                .anyMatch(rootResources::containsKey)) {
            throw new IllegalStateException(
                    "resource-scoped root requires its lifecycle context");
        }
        for (ReferenceRoot root : requestedRoots) {
            if (deletionTombstones.containsKey(key(root.tenantId(), root.digest()))) {
                throw new IllegalStateException(
                        "reference root publication is blocked by an unresolved deletion");
            }
        }
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
            ReferenceRoot root = new ReferenceRoot(requested.tenantId(), requested.kind(),
                    requested.rootId(), requested.digest(), publicationGeneration);
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
    public synchronized long publishDurableReferenceRoots(
            List<ReferenceRoot> requestedRoots,
            DurableObjectEnsurer durableObjectEnsurer
    ) {
        requireOneRootSet(requestedRoots);
        Objects.requireNonNull(durableObjectEnsurer, "durableObjectEnsurer");
        Map<RootObjectKey, ReferenceRoot> priorRoots = new LinkedHashMap<>(roots);
        Map<RootObjectKey, Long> priorReleasedRoots = new LinkedHashMap<>(releasedRoots);
        Map<String, String> priorTombstones = new LinkedHashMap<>(deletionTombstones);
        try {
            ReferenceRoot first = requestedRoots.get(0);
            ensureNoActiveDeletionTombstones(first.tenantId(), requestedRoots.stream()
                    .map(ReferenceRoot::digest).toList());
            durableObjectEnsurer.ensureDurable();
            clearRepairableDeletionTombstones(first.tenantId(), requestedRoots.stream()
                    .map(ReferenceRoot::digest).toList());
            return addReferenceRoots(requestedRoots);
        } catch (RuntimeException | Error failure) {
            roots.clear();
            roots.putAll(priorRoots);
            releasedRoots.clear();
            releasedRoots.putAll(priorReleasedRoots);
            deletionTombstones.clear();
            deletionTombstones.putAll(priorTombstones);
            throw failure;
        }
    }

    @Override
    public synchronized long publishDurableResourceReferenceRoots(
            ResourceLifecycle resource,
            List<ReferenceRoot> requestedRoots,
            DurableObjectEnsurer durableObjectEnsurer
    ) {
        Objects.requireNonNull(resource, "resource");
        ReferenceRoot first = requireOneRootSet(requestedRoots);
        Objects.requireNonNull(durableObjectEnsurer, "durableObjectEnsurer");
        if (!resource.tenantId().equals(first.tenantId())) {
            throw new IllegalArgumentException("resource and roots must share a tenant");
        }
        Map<RootObjectKey, ReferenceRoot> priorRoots = new LinkedHashMap<>(roots);
        Map<RootObjectKey, Long> priorReleasedRoots = new LinkedHashMap<>(releasedRoots);
        Map<RootObjectKey, ResourceLifecycle> priorRootResources =
                new LinkedHashMap<>(rootResources);
        Map<String, String> priorTombstones = new LinkedHashMap<>(deletionTombstones);
        try {
            requireExactActiveResource(resource);
            for (ReferenceRoot root : requestedRoots) {
                ResourceLifecycle existing = rootResources.get(rootKey(root));
                if (existing != null && !sameIncarnation(existing, resource)
                        && !releasedRoots.containsKey(rootKey(root))) {
                    throw new IllegalStateException(
                            "active root is owned by another resource incarnation");
                }
            }
            ensureNoActiveDeletionTombstones(first.tenantId(), requestedRoots.stream()
                    .map(ReferenceRoot::digest).toList());
            durableObjectEnsurer.ensureDurable();
            clearRepairableDeletionTombstones(first.tenantId(), requestedRoots.stream()
                    .map(ReferenceRoot::digest).toList());
            long generation = addReferenceRoots(requestedRoots, true);
            for (ReferenceRoot requested : requestedRoots) {
                rootResources.put(rootKey(requested), resource);
            }
            return generation;
        } catch (RuntimeException | Error failure) {
            roots.clear();
            roots.putAll(priorRoots);
            releasedRoots.clear();
            releasedRoots.putAll(priorReleasedRoots);
            rootResources.clear();
            rootResources.putAll(priorRootResources);
            deletionTombstones.clear();
            deletionTombstones.putAll(priorTombstones);
            throw failure;
        }
    }

    @Override
    public synchronized ResourceLifecycle beginResourceRetirement(
            String tenantId,
            ResourceKind resourceKind,
            String resourceId,
            long transitionedAtEpochMillis
    ) {
        requireTransitionTime(transitionedAtEpochMillis);
        CasText.required(tenantId, "tenantId");
        Objects.requireNonNull(resourceKind, "resourceKind");
        CasText.required(resourceId, "resourceId");
        ResourceLifecycle observed = resourceLifecycles.get(
                new ResourceKey(tenantId, resourceKind, resourceId));
        if (observed != null && observed.state() == ResourceLifecycleState.RETIRING) {
            return observed;
        }
        if (observed != null && observed.state() == ResourceLifecycleState.RETIRED) {
            throw new IllegalStateException("CAS resource is already RETIRED");
        }
        ResourceLifecycle current = ensureActiveResource(tenantId, resourceKind, resourceId);
        ResourceLifecycle retiring = new ResourceLifecycle(
                current.tenantId(), current.resourceKind(), current.resourceId(),
                current.tenantEpoch(), current.resourceEpoch(),
                ResourceLifecycleState.RETIRING, transitionedAtEpochMillis, 0);
        resourceLifecycles.put(resourceKey(current), retiring);
        return retiring;
    }

    @Override
    public synchronized ResourceLifecycle finalizeResourceRetirement(
            ResourceLifecycle retiring,
            long transitionedAtEpochMillis
    ) {
        Objects.requireNonNull(retiring, "retiring");
        requireTransitionTime(transitionedAtEpochMillis);
        ResourceLifecycle current = resourceLifecycles.get(resourceKey(retiring));
        if (current == null || !sameIncarnation(current, retiring)
                || current.state() != ResourceLifecycleState.RETIRING
                || retiring.state() != ResourceLifecycleState.RETIRING) {
            throw new IllegalStateException("resource retirement token is stale or invalid");
        }
        boolean activeMappedRoot = rootResources.entrySet().stream()
                .anyMatch(entry -> sameIncarnation(entry.getValue(), retiring)
                        && !releasedRoots.containsKey(entry.getKey()));
        if (activeMappedRoot) {
            throw new IllegalStateException(
                    "resource retirement has unreconciled active snapshot roots");
        }
        // A pre-V76/unscoped root over one of this resource's objects cannot be attributed
        // safely.  It blocks retirement rather than being guessed away.
        Set<String> boundDigests = resourceBindings.entrySet().stream()
                .filter(entry -> sameResource(entry.getKey(), retiring))
                .filter(entry -> !releasedResourceBindings.containsKey(entry.getKey()))
                .map(entry -> entry.getKey().digestHex())
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
        boolean activeUnmappedRoot = roots.entrySet().stream()
                .anyMatch(entry -> boundDigests.contains(entry.getKey().digestHex())
                        && !releasedRoots.containsKey(entry.getKey())
                        && !rootResources.containsKey(entry.getKey()));
        if (activeUnmappedRoot) {
            throw new IllegalStateException(
                    "resource retirement is blocked by an unscoped legacy root");
        }
        long released = 0;
        for (Map.Entry<BindingKey, ResourceBinding> entry : resourceBindings.entrySet()) {
            if (sameResource(entry.getKey(), retiring)
                    && !releasedResourceBindings.containsKey(entry.getKey())) {
                if (transitionedAtEpochMillis < entry.getValue().boundAtEpochMillis()) {
                    throw new IllegalArgumentException(
                            "retirement cannot precede resource binding");
                }
                releasedResourceBindings.put(entry.getKey(), transitionedAtEpochMillis);
                released++;
            }
        }
        ResourceLifecycle retired = new ResourceLifecycle(
                current.tenantId(), current.resourceKind(), current.resourceId(),
                current.tenantEpoch(), current.resourceEpoch(),
                ResourceLifecycleState.RETIRED, transitionedAtEpochMillis, released);
        resourceLifecycles.put(resourceKey(current), retired);
        return retired;
    }

    @Override
    public synchronized ResourceLifecycle reactivateResource(
            ResourceLifecycle retired,
            long transitionedAtEpochMillis
    ) {
        Objects.requireNonNull(retired, "retired");
        requireTransitionTime(transitionedAtEpochMillis);
        ResourceLifecycle current = resourceLifecycles.get(resourceKey(retired));
        if (current == null || !sameIncarnation(current, retired)
                || current.state() != ResourceLifecycleState.RETIRED
                || retired.state() != ResourceLifecycleState.RETIRED) {
            throw new IllegalStateException("resource reactivation token is stale or invalid");
        }
        TenantLifecycle tenant = requireTenantActive(retired.tenantId());
        ResourceLifecycle active = new ResourceLifecycle(
                retired.tenantId(), retired.resourceKind(), retired.resourceId(),
                tenant.epoch(), Math.addExact(retired.resourceEpoch(), 1),
                ResourceLifecycleState.ACTIVE, transitionedAtEpochMillis, 0);
        resourceLifecycles.put(resourceKey(retired), active);
        return active;
    }

    @Override
    public synchronized CasGarbageCollector.AtomicDeletionOutcome deleteIfUnreferenced(
            CasGarbageCollector.Candidate candidate,
            TenantCasStore tenantStore
    ) {
        Objects.requireNonNull(candidate, "candidate");
        Objects.requireNonNull(tenantStore, "tenantStore");
        if (tenantStore.deletionScope() != TenantCasStore.DeletionScope.TENANT_ISOLATED) {
            return CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE;
        }
        CasStore store = tenantStore.forTenant(candidate.tenantId());
        String objectKey = key(candidate.tenantId(), candidate.digest());
        String priorDeletionState = deletionTombstones.get(objectKey);
        if ("PENDING".equals(priorDeletionState)
                || "OUTCOME_UNKNOWN".equals(priorDeletionState)) {
            return CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE;
        }
        CatalogEntry entry = entries.get(objectKey);
        if (entry == null || !entry.digest().equals(candidate.digest())) {
            return CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE;
        }
        boolean rooted = roots.entrySet().stream()
                .anyMatch(root -> root.getValue().tenantId().equals(candidate.tenantId())
                        && root.getValue().digest().equals(candidate.digest())
                        && !releasedRoots.containsKey(root.getKey()));
        boolean resourceBound = resourceBindings.entrySet().stream()
                .anyMatch(binding -> binding.getValue().tenantId().equals(candidate.tenantId())
                        && binding.getValue().digest().equals(candidate.digest())
                        && !releasedResourceBindings.containsKey(binding.getKey()));
        if (entry.legalHold() || rooted || resourceBound) {
            return CasGarbageCollector.AtomicDeletionOutcome.LIVE_REFERENCE_OR_HOLD;
        }
        deletionTombstones.put(objectKey, "PENDING");
        try {
            boolean deleted = store.delete(candidate.digest());
            boolean stillPresent = store.contains(candidate.digest());
            if (!deleted) {
                deletionTombstones.put(objectKey, stillPresent ? "FAILED" : "MISSING");
                return stillPresent
                        ? CasGarbageCollector.AtomicDeletionOutcome.FAILED
                        : CasGarbageCollector.AtomicDeletionOutcome.NOT_FOUND;
            }
            if (stillPresent) {
                deletionTombstones.put(objectKey, "FAILED");
                return CasGarbageCollector.AtomicDeletionOutcome.FAILED;
            }
            deletionTombstones.put(objectKey, "DELETED");
            return CasGarbageCollector.AtomicDeletionOutcome.DELETED;
        } catch (RuntimeException ambiguous) {
            deletionTombstones.put(objectKey, "OUTCOME_UNKNOWN");
            return CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE;
        }
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
    public synchronized boolean releaseReferenceRootGeneration(
            String tenantId,
            CasGarbageCollector.RootKind kind,
            String rootId,
            long expectedGeneration,
            long releasedAtEpochMillis
    ) {
        CasText.required(tenantId, "tenantId");
        Objects.requireNonNull(kind, "kind");
        CasText.required(rootId, "rootId");
        if (expectedGeneration < 0 || releasedAtEpochMillis < expectedGeneration) {
            throw new IllegalArgumentException("reference root generation/release is invalid");
        }
        List<RootObjectKey> matching = roots.keySet().stream()
                .filter(key -> key.tenantId().equals(tenantId))
                .filter(key -> key.kind() == kind)
                .filter(key -> key.rootId().equals(rootId))
                .filter(key -> !releasedRoots.containsKey(key))
                .toList();
        boolean allExpectedGeneration = matching.stream().map(roots::get)
                .allMatch(root -> root.createdAtEpochMillis() == expectedGeneration);
        if (matching.isEmpty() || !allExpectedGeneration) {
            return false;
        }
        matching.forEach(key -> releasedRoots.put(key, releasedAtEpochMillis));
        return true;
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
    public synchronized List<ReferenceRoot> activeReferenceRoots(
            String tenantId,
            CasGarbageCollector.RootKind kind,
            String rootId
    ) {
        CasText.required(tenantId, "tenantId");
        Objects.requireNonNull(kind, "kind");
        CasText.required(rootId, "rootId");
        return roots.entrySet().stream()
                .filter(entry -> entry.getKey().tenantId().equals(tenantId))
                .filter(entry -> entry.getKey().kind() == kind)
                .filter(entry -> entry.getKey().rootId().equals(rootId))
                .filter(entry -> !releasedRoots.containsKey(entry.getKey()))
                .map(Map.Entry::getValue)
                .toList();
    }

    @Override
    public synchronized void setLegalHold(String tenantId, CasDigest digest, boolean legalHold) {
        if (legalHold && deletionTombstones.containsKey(key(tenantId, digest))) {
            throw new IllegalStateException(
                    "a legal hold cannot be attached while object deletion is unresolved");
        }
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

    private void ensureNoActiveDeletionTombstones(
            String tenantId, List<CasDigest> digests) {
        for (CasDigest digest : digests) {
            String state = deletionTombstones.get(key(tenantId, digest));
            if ("PENDING".equals(state) || "OUTCOME_UNKNOWN".equals(state)) {
                throw new IllegalStateException(
                        "durable publication is blocked by active or ambiguous deletion state "
                                + state);
            }
        }
    }

    private void clearRepairableDeletionTombstones(
            String tenantId, List<CasDigest> digests) {
        for (CasDigest digest : digests) {
            String objectKey = key(tenantId, digest);
            String state = deletionTombstones.get(objectKey);
            if (state == null) {
                continue;
            }
            if (Set.of("DELETED", "MISSING", "FAILED").contains(state)) {
                deletionTombstones.remove(objectKey);
                continue;
            }
            throw new IllegalStateException(
                    "deletion tombstone is not repairable without reconciliation: " + state);
        }
    }

    private static void requireResourceLookup(String tenantId, ResourceKind resourceKind,
                                              String resourceId, CasDigest digest) {
        CasText.required(tenantId, "tenantId");
        Objects.requireNonNull(resourceKind, "resourceKind");
        CasText.required(resourceId, "resourceId");
        Objects.requireNonNull(digest, "digest");
    }

    private TenantLifecycle requireTenantActive(String tenantId) {
        CasText.required(tenantId, "tenantId");
        TenantLifecycle tenant = tenantLifecycles.computeIfAbsent(
                tenantId, ignored -> new TenantLifecycle(
                        1, ResourceLifecycleState.ACTIVE, 0));
        if (tenant.state() != ResourceLifecycleState.ACTIVE) {
            throw new IllegalStateException("CAS tenant is not ACTIVE");
        }
        return tenant;
    }

    private void requireExactActiveResource(ResourceLifecycle supplied) {
        supplied.requireActive();
        TenantLifecycle tenant = requireTenantActive(supplied.tenantId());
        ResourceLifecycle current = resourceLifecycles.get(resourceKey(supplied));
        if (current == null || current.state() != ResourceLifecycleState.ACTIVE
                || tenant.epoch() != supplied.tenantEpoch()
                || !sameIncarnation(current, supplied)) {
            throw new IllegalStateException("CAS resource lifecycle token is stale or inactive");
        }
    }

    private static void requireBindingResource(
            ResourceBinding binding, ResourceLifecycle resource) {
        if (!binding.tenantId().equals(resource.tenantId())
                || binding.resourceKind() != resource.resourceKind()
                || !binding.resourceId().equals(resource.resourceId())) {
            throw new IllegalArgumentException(
                    "binding and resource lifecycle identify different resources");
        }
    }

    private static boolean sameIncarnation(
            ResourceLifecycle left, ResourceLifecycle right) {
        return left.tenantId().equals(right.tenantId())
                && left.resourceKind() == right.resourceKind()
                && left.resourceId().equals(right.resourceId())
                && left.tenantEpoch() == right.tenantEpoch()
                && left.resourceEpoch() == right.resourceEpoch();
    }

    private static boolean sameResource(BindingKey key, ResourceLifecycle resource) {
        return key.tenantId().equals(resource.tenantId())
                && key.resourceKind() == resource.resourceKind()
                && key.resourceId().equals(resource.resourceId());
    }

    private static void requireTransitionTime(long transitionedAtEpochMillis) {
        if (transitionedAtEpochMillis < 0) {
            throw new IllegalArgumentException("lifecycle transition time must not be negative");
        }
    }
}
