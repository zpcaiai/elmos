package io.elmos.snapshot;

import io.elmos.scm.EphemeralCredential;
import java.io.InputStream;
import java.nio.file.Path;

public final class SnapshotPorts {
    private SnapshotPorts() {}

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
        String putIfAbsent(String sha256, long size, InputStream content, String mediaType);
    }

    /**
     * Read access is deliberately separate from writes so a production
     * deployment can give the materializer only content-addressed read rights.
     */
    public interface ArtifactReader {
        InputStream open(String reference);
    }

    public interface SnapshotStore {
        SnapshotModel.RepositorySnapshot findReusable(String repositoryId, String commitSha, int schemaVersion);
        SnapshotModel.RepositorySnapshot saveAvailable(SnapshotModel.RepositorySnapshot snapshot);
    }
}
