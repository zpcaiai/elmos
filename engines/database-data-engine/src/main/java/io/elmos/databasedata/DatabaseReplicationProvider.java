package io.elmos.databasedata;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/** External Runner port. Implementations must not be loaded into the control plane. */
public interface DatabaseReplicationProvider {
    record SnapshotRequest(String organizationId, String estateRef, String credentialLeaseRef) {}
    record SnapshotResult(String snapshotRef, String sourcePosition, String offsetType,
                          Instant capturedAt, List<String> evidenceRefs) {}
    record InitialLoadRequest(String snapshotRef, String targetRef, long maximumChunkBytes) {}
    record InitialLoadResult(String runId, String snapshotPosition, long rowsLoaded,
                             long bytesLoaded, List<String> evidenceRefs) {}
    record CdcStreamRef(String streamId, String provider, String startPosition,
                        String offsetType, List<String> evidenceRefs) {}
    record CdcStatus(String streamId, String sourcePosition, String appliedPosition,
                     long recordLag, double timeLagSeconds, int openTransactions,
                     boolean offsetRecoverable, List<String> evidenceRefs) {}
    record CutoverFrontier(String streamId, String sourcePosition, String appliedPosition,
                           boolean consistent, Map<String, String> tableFrontiers,
                           List<String> evidenceRefs) {}

    SnapshotResult createSnapshot(SnapshotRequest request);
    InitialLoadResult load(InitialLoadRequest request);
    CdcStreamRef startCdc(String snapshotRef, String approvedOperationRef);
    CdcStatus status(CdcStreamRef stream);
    CutoverFrontier frontier(CdcStreamRef stream);
    void stop(CdcStreamRef stream, String approvedOperationRef);
}
