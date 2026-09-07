package io.elmos.cas;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.function.Function;

/**
 * ELMOS-CAS-037/038. Compares what the control plane believes exists against what the store
 * actually holds.
 *
 * <p>The two directions of drift fail differently and both are silent:
 *
 * <ul>
 *   <li>A <b>missing blob</b> - referenced by a snapshot, an evidence pack or a cached result but
 *       absent from storage - is a build that will fail at materialisation time, days after the
 *       reference was written, with an error that points at the consumer rather than the cause.</li>
 *   <li>An <b>orphan</b> - present but referenced by nothing - is a bill. Harmless until it is
 *       most of the bucket.</li>
 * </ul>
 *
 * <p>This class only reports. Deleting is the collector's job, under its own policy, and keeping
 * the two apart is what stops a stale reference table from becoming a data-loss event.
 */
public final class CasReconciler {

    public record Finding(CasDigest digest, String detail) {
    }

    public record ReconciliationReport(List<Finding> missingBlobs,
                                       List<Finding> orphanedObjects,
                                       List<Finding> danglingManifests,
                                       List<String> incompleteUploadSessions,
                                       long orphanedBytes,
                                       long atEpochMillis) {
        public ReconciliationReport {
            missingBlobs = List.copyOf(missingBlobs);
            orphanedObjects = List.copyOf(orphanedObjects);
            danglingManifests = List.copyOf(danglingManifests);
            incompleteUploadSessions = List.copyOf(incompleteUploadSessions);
        }

        public boolean clean() {
            return missingBlobs.isEmpty() && orphanedObjects.isEmpty() && danglingManifests.isEmpty()
                    && incompleteUploadSessions.isEmpty();
        }
    }

    private final CasStore store;
    private final Function<CasDigest, Optional<CasManifest>> manifestResolver;

    public CasReconciler(CasStore store, Function<CasDigest, Optional<CasManifest>> manifestResolver) {
        this.store = store;
        this.manifestResolver = manifestResolver;
    }

    /**
     * @param declaredReferences every digest the control plane claims to reference, by owner, so a
     *                           missing object can be attributed to the record that points at it
     * @param catalog            object metadata, used to age orphans
     * @param minimumOrphanAge   objects newer than this are skipped: they are more likely to be
     *                           mid-transaction than abandoned
     */
    public ReconciliationReport reconcile(Map<String, List<CasDigest>> declaredReferences,
                                          Map<CasDigest, CasObjectModel.ObjectMetadata> catalog,
                                          Optional<ResumableUploadService> uploads,
                                          long minimumOrphanAge,
                                          long nowEpochMillis) {
        List<Finding> missing = new ArrayList<>();
        List<Finding> dangling = new ArrayList<>();
        Set<CasDigest> referenced = new LinkedHashSet<>();

        declaredReferences.forEach((owner, digests) -> {
            for (CasDigest digest : digests) {
                referenced.add(digest);
                Optional<CasManifest> manifest = manifestResolver.apply(digest);
                if (manifest.isPresent()) {
                    List<CasDigest> broken = new ArrayList<>();
                    for (CasDigest child : manifest.get().directReferences()) {
                        referenced.add(child);
                        if (!store.contains(child)) {
                            broken.add(child);
                        }
                    }
                    if (!broken.isEmpty()) {
                        dangling.add(new Finding(digest, owner + " manifest references absent objects " + broken));
                        broken.forEach(child -> missing.add(new Finding(child, "referenced by manifest " + digest.compact())));
                    }
                    continue;
                }
                if (!store.contains(digest)) {
                    missing.add(new Finding(digest, "referenced by " + owner));
                }
            }
        });

        List<Finding> orphans = new ArrayList<>();
        long orphanedBytes = 0;
        for (CasDigest digest : store.inventory()) {
            if (referenced.contains(digest)) {
                continue;
            }
            CasObjectModel.ObjectMetadata metadata = catalog.get(digest);
            long age = metadata == null ? Long.MAX_VALUE : nowEpochMillis - metadata.createdAtEpochMillis();
            if (age < minimumOrphanAge) {
                continue;
            }
            orphans.add(new Finding(digest, metadata == null
                    ? "present in store but absent from the object catalogue"
                    : "unreferenced since " + metadata.createdAtEpochMillis()));
            orphanedBytes += digest.sizeBytes();
        }

        List<String> incomplete = uploads
                .map(service -> service.incompleteSessions().stream()
                        .map(session -> session.sessionId() + ":" + session.state()
                                + ":missing=" + session.missingChunks().size())
                        .toList())
                .orElse(List.of());

        return new ReconciliationReport(missing, orphans, dangling, incomplete, orphanedBytes, nowEpochMillis);
    }
}
