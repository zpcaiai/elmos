package io.elmos.snapshot;

import io.elmos.scm.EphemeralCredential;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.List;

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

    public interface RefResolver { ResolvedRef resolve(String repositoryId, String requestedRef, EphemeralCredential credential); }
    public record ResolvedRef(String commitSha, String treeSha, String fetchRef) {
        public ResolvedRef(String commitSha, String treeSha) { this(commitSha, treeSha, commitSha); }
    }

    public interface SourceFetcher { FetchedSource fetch(String repositoryId, ResolvedRef ref, EphemeralCredential credential); }
    public record FetchedSource(Path path, String treeSha, AutoCloseable cleanup) implements AutoCloseable {
        public FetchedSource(Path path, AutoCloseable cleanup) { this(path, null, cleanup); }
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
         * Releases all reachability records owned by {@code snapshotId}. The call must be
         * idempotent so capture failure compensation and a later lifecycle retry are both safe.
         */
        default void releaseSnapshot(ArtifactResourceContext resource, String snapshotId) {
            // A store without a collector has no reachability catalogue to update.
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
        SnapshotModel.RepositorySnapshot findReusable(String repositoryId, String commitSha, int schemaVersion);
        SnapshotModel.RepositorySnapshot saveAvailable(SnapshotModel.RepositorySnapshot snapshot);
    }
}
