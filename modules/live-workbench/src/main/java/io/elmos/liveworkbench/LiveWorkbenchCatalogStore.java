package io.elmos.liveworkbench;

import java.util.List;
import java.util.Optional;

import static io.elmos.liveworkbench.LiveWorkbenchService.ArtifactDelivery;
import static io.elmos.liveworkbench.LwContracts.*;
import static io.elmos.liveworkbench.ProductionContracts.*;

/** Immutable, tenant-scoped catalog behind the read/teach/learn workbench surfaces. */
public interface LiveWorkbenchCatalogStore {
    RuntimeProfile registerProfile(String tenantId, RuntimeProfile profile, long now);
    Optional<RuntimeProfile> profile(String tenantId, String profileId);
    ArtifactDelivery registerDelivery(String tenantId, ArtifactDelivery delivery, long now);
    Optional<ArtifactDelivery> delivery(String tenantId, String deliveryId);
    SourceAnchor registerAnchor(String tenantId, String anchorId, SourceAnchor anchor, long now);
    Optional<SourceAnchor> anchor(String tenantId, String anchorId);
    EvidenceClaim registerClaim(String tenantId, EvidenceClaim claim, long now);
    List<EvidenceClaim> claimsForAnchor(String tenantId, String anchorId);
    LearningMission registerMission(String tenantId, LearningMission mission, long now);
    Optional<LearningMission> mission(String tenantId, String missionId);
    SemanticCorrespondence registerCorrespondence(String tenantId, SemanticCorrespondence correspondence, long now);
    Optional<SemanticCorrespondence> correspondence(String tenantId, String mappingId);
    record AttemptReservation(MissionAttemptReceipt receipt, boolean created) {}
    AttemptReservation reserveAttempt(String tenantId, String actorId, String missionId, MissionAttemptRequest request,
                                      String attemptId, String idempotencyKey, String requestDigest, long now);
    MissionAttemptReceipt completeAttempt(String tenantId, String actorId, String missionId, String idempotencyKey,
                                          MissionAttemptReceipt receipt, long now);
    int invalidateSnapshot(String tenantId, String snapshotId);
}
