package io.elmos.snapshot;

import io.elmos.scm.EphemeralCredential;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class SnapshotPorts {
    private SnapshotPorts() {}

    /**
     * Trusted ownership context for an artifact operation.
     *
     * <p>The content digest is deliberately not an authorization boundary: two organizations can
     * produce byte-identical archives. Callers must therefore carry the organization and
     * repository that were authorized for the capture or materialization all the way to the
     * artifact adapter.
     */
    public record ArtifactResourceContext(String organizationId, String repositoryId) {
        public ArtifactResourceContext {
            organizationId = requireResourceId(organizationId, "organizationId");
            repositoryId = requireResourceId(repositoryId, "repositoryId");
        }

        private static String requireResourceId(String value, String field) {
            if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")) {
                throw new IllegalArgumentException(field
                        + " must be a safe identifier of at most 64 characters");
            }
            return value;
        }
    }

    public interface RefResolver {
        ResolvedRef resolve(
                ArtifactResourceContext resource,
                String requestedRef,
                EphemeralCredential credential
        );
    }
    public record ResolvedRef(String commitSha, String treeSha, String fetchRef) {
        public ResolvedRef(String commitSha, String treeSha) { this(commitSha, treeSha, commitSha); }
    }

    public interface SourceFetcher {
        FetchedSource fetch(
                ArtifactResourceContext resource,
                ResolvedRef ref,
                EphemeralCredential credential
        );
    }
    public record FetchedSource(
            Path path,
            String treeSha,
            DeterministicSnapshotArchiver.SourceLease sourceLease,
            AutoCloseable cleanup
    ) implements AutoCloseable {
        public FetchedSource {
            path = Objects.requireNonNull(path, "path");
            sourceLease = Objects.requireNonNull(sourceLease, "sourceLease");
            cleanup = Objects.requireNonNull(cleanup, "cleanup");
        }
        public FetchedSource(Path path, AutoCloseable cleanup) {
            this(path, null, DeterministicSnapshotArchiver.localSelfAttestedLease(), cleanup);
        }
        public FetchedSource(Path path, String treeSha, AutoCloseable cleanup) {
            this(path, treeSha, DeterministicSnapshotArchiver.localSelfAttestedLease(), cleanup);
        }
        @Override public void close() throws Exception { cleanup.close(); }
    }
    public interface RepositoryCredentialBroker {
        EphemeralCredential issue(String organizationId, String repositoryId,
                                  long repositoryExternalId, long installationExternalId);
    }

    public interface ArtifactStore {
        String putIfAbsent(ArtifactResourceContext resource, String sha256, long size,
                           InputStream content, String mediaType);

        /**
         * Makes every supplied artifact reachable for the lifetime of one immutable snapshot.
         *
         * <p>The operation is a batch contract: an implementation that cannot retain every
         * reference must compensate any partial retention before it throws. Implementations that
         * do not perform garbage collection (for example the legacy local store) may keep the
         * default no-op, but a collector-aware implementation must fail closed for malformed,
         * missing, corrupt, or unauthorized references.
         */
        default void retainSnapshot(ArtifactResourceContext resource, String snapshotId,
                                    List<String> references) {
            // A store without a collector has no reachability catalogue to update.
        }

        /**
         * Retains one logical snapshot and returns the exact collector generation that was
         * observed or created by the operation.
         *
         * <p>Lifecycle callers must preserve this token until the database transition that makes
         * the snapshot unreachable has committed. Passing a token back to
         * {@link #releaseSnapshotGeneration} prevents a delayed delete acknowledgement from
         * releasing a newer root generation that another process has reactivated.
         */
        default ArtifactRetention retainSnapshotGeneration(
                ArtifactResourceContext resource,
                String snapshotId,
                List<String> references
        ) {
            retainSnapshot(resource, snapshotId, references);
            return ArtifactRetention.untracked(snapshotId);
        }

        /**
         * Releases all reachability records owned by {@code snapshotId}. The call must be
         * idempotent so capture failure compensation and a later lifecycle retry are both safe.
         */
        default void releaseSnapshot(ArtifactResourceContext resource, String snapshotId) {
            // A store without a collector has no reachability catalogue to update.
        }

        /**
         * Releases only the root generation named by {@code retention}. Collector-aware stores
         * must reject missing or foreign generation tokens instead of falling back to a
         * wall-clock release.
         */
        default void releaseSnapshotGeneration(
                ArtifactResourceContext resource,
                ArtifactRetention retention
        ) {
            Objects.requireNonNull(retention, "retention");
            releaseSnapshot(resource, retention.snapshotId());
        }
    }

    /**
     * Opaque, persistence-safe collector generation token.
     *
     * <p>The map permits a compatibility adapter to preserve independent backend generations
     * without making the snapshot module depend on a concrete CAS implementation. Empty maps are
     * valid only for stores that do not perform garbage collection.
     */
    public record ArtifactRetention(String snapshotId, Map<String, Long> generations) {
        public ArtifactRetention {
            if (snapshotId == null
                    || !snapshotId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")) {
                throw new IllegalArgumentException("snapshotId must be a safe identifier");
            }
            Objects.requireNonNull(generations, "generations");
            Map<String, Long> copy = new LinkedHashMap<>();
            generations.forEach((name, generation) -> {
                if (name == null || !name.matches("[a-z][a-z0-9.-]{0,63}")) {
                    throw new IllegalArgumentException("artifact retention generation name is invalid");
                }
                if (generation == null || generation < 0) {
                    throw new IllegalArgumentException("artifact retention generation is invalid");
                }
                if (copy.putIfAbsent(name, generation) != null) {
                    throw new IllegalArgumentException("duplicate artifact retention generation");
                }
            });
            generations = Map.copyOf(copy);
        }

        public static ArtifactRetention untracked(String snapshotId) {
            return new ArtifactRetention(snapshotId, Map.of());
        }

        public ArtifactRetention merge(ArtifactRetention other) {
            Objects.requireNonNull(other, "other");
            if (!snapshotId.equals(other.snapshotId)) {
                throw new IllegalArgumentException("cannot merge different snapshot retentions");
            }
            Map<String, Long> merged = new LinkedHashMap<>(generations);
            other.generations.forEach((name, generation) -> {
                Long previous = merged.putIfAbsent(name, generation);
                if (previous != null && !previous.equals(generation)) {
                    throw new IllegalStateException("artifact retention generations conflict");
                }
            });
            return new ArtifactRetention(snapshotId, merged);
        }

        public long requireGeneration(String name) {
            Long generation = generations.get(name);
            if (generation == null) {
                throw new IllegalArgumentException(
                        "artifact retention does not contain generation " + name);
            }
            return generation;
        }
    }

    /**
     * Read access is deliberately separate from writes so a production
     * deployment can give the materializer only content-addressed read rights.
     */
    public interface ArtifactReader {
        InputStream open(ArtifactResourceContext resource, String reference);
    }

    public interface SnapshotStore {
        SnapshotModel.RepositorySnapshot findReusable(String organizationId, String repositoryId,
                                                        String commitSha, int schemaVersion);
        SnapshotModel.RepositorySnapshot saveAvailable(SnapshotModel.RepositorySnapshot snapshot);
    }
}
