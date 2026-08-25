package io.elmos.cas;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.function.Function;
import java.util.function.LongSupplier;

/**
 * ELMOS-CAS-033 through ELMOS-CAS-036. Reachability-based collection.
 *
 * <p>The collector is the one component in a CAS that can destroy something it cannot rebuild, so
 * every default here leans toward keeping bytes:
 *
 * <ul>
 *   <li>An object of <b>unknown</b> reachability is retained, never collected. If a manifest
 *       cannot be resolved, the run reports it and keeps everything under it.</li>
 *   <li>A legal hold outranks everything, including an explicit tenant deletion.</li>
 *   <li>A minimum age shields objects that were written between the mark and the sweep. Without
 *       it, an action that stores an output and registers its reference a second later is a race
 *       the collector wins by deleting live data.</li>
 * </ul>
 *
 * <p>Every run produces a deletion manifest whether or not it deleted anything, because "the
 * collector considered and kept this" is the record you need when an object goes missing.
 */
public final class CasGarbageCollector {

    public enum RootKind {
        SNAPSHOT,
        STAGING,
        WORKFLOW,
        EVIDENCE,
        RELEASE,
        LEGAL_HOLD,
        ACTION_CACHE
    }

    private enum RootExpansion {
        LEAF,
        TREE,
        UNRESOLVED
    }

    public record ReferenceRoot(RootKind kind, String id, String tenantId, List<CasDigest> digests) {
        public ReferenceRoot {
            Objects.requireNonNull(kind, "kind");
            id = CasText.required(id, "id");
            tenantId = CasText.required(tenantId, "tenantId");
            digests = List.copyOf(digests);
            if (digests.isEmpty()) {
                throw new IllegalArgumentException("reference root must retain at least one digest");
            }
        }
    }

    public record CollectionPolicy(boolean dryRun,
                                   long minimumAgeMillis,
                                   Set<CasObjectModel.RetentionClass> collectable,
                                   Set<CasDigest> legalHoldObjects,
                                   Set<String> legalHoldTenants,
                                   Set<String> tenantsPendingDeletion) {
        public CollectionPolicy {
            if (minimumAgeMillis < 0) {
                throw new IllegalArgumentException("minimumAgeMillis must not be negative");
            }
            collectable = Set.copyOf(collectable);
            legalHoldObjects = Set.copyOf(legalHoldObjects);
            legalHoldTenants = Set.copyOf(legalHoldTenants);
            tenantsPendingDeletion = Set.copyOf(tenantsPendingDeletion);
        }

        public static CollectionPolicy dryRun(long minimumAgeMillis) {
            return new CollectionPolicy(true, minimumAgeMillis,
                    Set.of(CasObjectModel.RetentionClass.EPHEMERAL, CasObjectModel.RetentionClass.STANDARD),
                    Set.of(), Set.of(), Set.of());
        }

        public CollectionPolicy executing() {
            return new CollectionPolicy(false, minimumAgeMillis, collectable, legalHoldObjects,
                    legalHoldTenants, tenantsPendingDeletion);
        }
    }

    public record Candidate(CasDigest digest, long sizeBytes, String tenantId, String reason) {
        public Candidate {
            Objects.requireNonNull(digest, "digest");
            if (sizeBytes != digest.sizeBytes()) {
                throw new IllegalArgumentException("candidate size must match its digest identity");
            }
            tenantId = CasText.required(tenantId, "tenantId");
            reason = CasText.required(reason, "reason");
        }
    }

    public record Retained(CasDigest digest, String reason) {
        public Retained {
            Objects.requireNonNull(digest, "digest");
            reason = CasText.required(reason, "reason");
        }
    }

    public record DeletionManifest(String batchId,
                                   boolean dryRun,
                                   List<Candidate> collected,
                                   List<Retained> retained,
                                   List<CasDigest> unresolvedReferences,
                                   long reclaimedBytes,
                                   long atEpochMillis) {
        public DeletionManifest {
            batchId = CasText.required(batchId, "batchId");
            collected = List.copyOf(collected);
            retained = List.copyOf(retained);
            unresolvedReferences = List.copyOf(unresolvedReferences);
            if (reclaimedBytes < 0 || atEpochMillis < 0) {
                throw new IllegalArgumentException(
                        "deletion manifest byte count and epoch must not be negative");
            }
        }

        public CasDigest digest() {
            CasManifest.CanonicalEncoder encoder = new CasManifest.CanonicalEncoder(
                    "elmos-deletion-manifest/2");
            encoder.field("batch_id", batchId);
            encoder.field("dry_run", Boolean.toString(dryRun));
            List<Candidate> canonicalCollected = collected.stream()
                    .sorted(java.util.Comparator.comparing(candidate -> candidate.digest().compact()))
                    .toList();
            encoder.field("collected_count", Integer.toString(canonicalCollected.size()));
            for (int index = 0; index < canonicalCollected.size(); index++) {
                Candidate candidate = canonicalCollected.get(index);
                String prefix = "collected_" + index + '_';
                encoder.field(prefix + "digest", candidate.digest().compact());
                encoder.field(prefix + "size_bytes", Long.toString(candidate.sizeBytes()));
                encoder.field(prefix + "tenant", candidate.tenantId());
                encoder.field(prefix + "reason", candidate.reason());
            }
            List<Retained> canonicalRetained = retained.stream()
                    .sorted(java.util.Comparator.comparing(entry -> entry.digest().compact()))
                    .toList();
            encoder.field("retained_count", Integer.toString(canonicalRetained.size()));
            for (int index = 0; index < canonicalRetained.size(); index++) {
                Retained entry = canonicalRetained.get(index);
                String prefix = "retained_" + index + '_';
                encoder.field(prefix + "digest", entry.digest().compact());
                encoder.field(prefix + "reason", entry.reason());
            }
            encoder.list("unresolved", unresolvedReferences.stream()
                    .map(CasDigest::compact).sorted().toList());
            encoder.field("reclaimed_bytes", Long.toString(reclaimedBytes));
            encoder.field("at_epoch_millis", Long.toString(atEpochMillis));
            return CasDigest.of(encoder.bytes());
        }
    }

    private final CasStore store;
    private final Function<CasDigest, Optional<CasManifest>> manifestResolver;
    private final LongSupplier clock;

    public CasGarbageCollector(CasStore store, Function<CasDigest, Optional<CasManifest>> manifestResolver,
                               LongSupplier clock) {
        this.store = store;
        this.manifestResolver = manifestResolver;
        this.clock = clock;
    }

    /**
     * ELMOS-CAS-034. Transitive closure of the roots.
     *
     * @param unresolved collects references that could not be expanded; the sweep treats their
     *                   whole subtree as unknown and therefore untouchable
     */
    public Set<CasDigest> markReachable(List<ReferenceRoot> roots, List<CasDigest> unresolved) {
        return markReachable(roots, unresolved, Map.of());
    }

    private Set<CasDigest> markReachable(
            List<ReferenceRoot> roots,
            List<CasDigest> unresolved,
            Map<CasDigest, CasObjectModel.ObjectMetadata> catalog
    ) {
        Set<CasDigest> reachable = new LinkedHashSet<>();
        Deque<CasDigest> pending = new ArrayDeque<>();
        roots.forEach(root -> pending.addAll(root.digests()));
        while (!pending.isEmpty()) {
            CasDigest digest = pending.pollFirst();
            if (!reachable.add(digest)) {
                continue;
            }
            Optional<CasManifest> manifest;
            try {
                manifest = manifestResolver.apply(digest);
            } catch (RuntimeException unreadableManifest) {
                addUnresolved(unresolved, digest);
                continue;
            }
            if (manifest.isPresent()) {
                CasManifest resolved = manifest.orElseThrow();
                if (!resolved.digest().equals(digest)) {
                    addUnresolved(unresolved, digest);
                    continue;
                }
                pending.addAll(resolved.directReferences());
                continue;
            }
            CasObjectModel.ObjectMetadata metadata = catalog.get(digest);
            if (metadata != null && (metadata.kind() == CasObjectModel.ObjectKind.MANIFEST
                    || metadata.kind() == CasObjectModel.ObjectKind.ACTION_RESULT)) {
                // Optional.empty is only authoritative for a known leaf.  For a catalogue entry
                // that promises a graph-bearing format it means the resolver did not establish
                // the edges, so sweeping would be unsafe even if the raw bytes are readable.
                addUnresolved(unresolved, digest);
                continue;
            }
            if (!store.contains(digest)) {
                addUnresolved(unresolved, digest);
                continue;
            }
            RootExpansion expansion = expandTree(digest, pending, unresolved);
            if (expansion == RootExpansion.LEAF
                    && (metadata == null || metadata.kind() == CasObjectModel.ObjectKind.TREE)) {
                // Without catalogue type information, Optional.empty cannot distinguish a real
                // leaf from a manifest that was temporarily unavailable.  Unknown roots and
                // catalogue-declared trees therefore fail closed.
                addUnresolved(unresolved, digest);
            }
        }
        return reachable;
    }

    public DeletionManifest collect(List<ReferenceRoot> roots,
                                    Map<CasDigest, CasObjectModel.ObjectMetadata> catalog,
                                    CollectionPolicy policy,
                                    String batchId) {
        long now = clock.getAsLong();
        if (now < 0) {
            throw new IllegalStateException("collector clock returned a negative epoch");
        }
        List<CasDigest> unresolved = new ArrayList<>();
        Set<CasDigest> reachable = markReachable(roots, unresolved, catalog);
        Set<CasDigest> heldByRoot = new LinkedHashSet<>();
        roots.stream().filter(root -> root.kind() == RootKind.LEGAL_HOLD)
                .forEach(root -> heldByRoot.addAll(root.digests()));

        List<Candidate> collected = new ArrayList<>();
        List<Retained> retained = new ArrayList<>();
        long reclaimed = 0;
        boolean unresolvedGraph = !unresolved.isEmpty();

        for (CasDigest digest : store.inventory()) {
            CasObjectModel.ObjectMetadata metadata = catalog.get(digest);
            String tenantId = metadata == null ? "unknown" : metadata.tenantId();

            if (policy.legalHoldObjects().contains(digest) || heldByRoot.contains(digest)
                    || (metadata != null && metadata.legalHold())
                    || (metadata != null && policy.legalHoldTenants().contains(metadata.tenantId()))) {
                retained.add(new Retained(digest, "LEGAL_HOLD"));
                continue;
            }
            if (reachable.contains(digest)) {
                retained.add(new Retained(digest, "REACHABLE"));
                continue;
            }
            if (unresolvedGraph) {
                // A failed root expansion means we cannot know which of the remaining objects are
                // descendants of that root.  There is no safe object-by-object approximation:
                // the missing edge is exactly the information a sweep would need.  Block the
                // whole sweep (including explicit tenant deletion) and let a later, healthy run
                // reconsider it.  Legal holds and known roots keep their more precise reasons.
                retained.add(new Retained(digest, "UNRESOLVED_ROOT_GRAPH"));
                continue;
            }
            if (metadata == null) {
                // Present in the store but absent from the catalogue. That is a reconciliation
                // finding, not a licence to delete: the reference may live in a system that was
                // unreachable when the roots were gathered.
                retained.add(new Retained(digest, "UNCATALOGUED"));
                continue;
            }
            boolean tenantDeleting = policy.tenantsPendingDeletion().contains(metadata.tenantId());
            if (!tenantDeleting && now - metadata.createdAtEpochMillis() < policy.minimumAgeMillis()) {
                retained.add(new Retained(digest, "YOUNGER_THAN_MINIMUM_AGE"));
                continue;
            }
            if (!tenantDeleting && !policy.collectable().contains(metadata.retentionClass())) {
                retained.add(new Retained(digest, "RETENTION_CLASS:" + metadata.retentionClass()));
                continue;
            }
            String reason = tenantDeleting ? "TENANT_DELETION" : "UNREACHABLE";
            collected.add(new Candidate(digest, digest.sizeBytes(), tenantId, reason));
            reclaimed += digest.sizeBytes();
            if (!policy.dryRun()) {
                store.delete(digest);
            }
        }
        return new DeletionManifest(batchId, policy.dryRun(), collected, retained, unresolved, reclaimed, now);
    }

    private RootExpansion expandTree(CasDigest digest, Deque<CasDigest> pending,
                                     List<CasDigest> unresolved) {
        byte[] content;
        try {
            content = store.get(digest);
        } catch (RuntimeException unreadable) {
            addUnresolved(unresolved, digest);
            return RootExpansion.UNRESOLVED;
        }
        if (content.length < MerkleTree.FORMAT.length()
                || !new String(content, 0, MerkleTree.FORMAT.length(), java.nio.charset.StandardCharsets.UTF_8)
                .equals(MerkleTree.FORMAT)) {
            return RootExpansion.LEAF;
        }
        List<CasDigest> children = new ArrayList<>();
        try {
            for (MerkleTree.Entry entry : MerkleTree.parse(content)) {
                if (entry.kind() != MerkleTree.EntryKind.SYMLINK) {
                    children.add(CasDigest.parseCompact(entry.payload()));
                }
            }
        } catch (RuntimeException malformedTree) {
            addUnresolved(unresolved, digest);
            return RootExpansion.UNRESOLVED;
        }
        pending.addAll(children);
        return RootExpansion.TREE;
    }

    private static void addUnresolved(List<CasDigest> unresolved, CasDigest digest) {
        if (!unresolved.contains(digest)) {
            unresolved.add(digest);
        }
    }
}
