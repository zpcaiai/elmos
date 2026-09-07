package io.elmos.liveworkbench;

import java.time.Clock;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import static io.elmos.liveworkbench.LiveWorkbenchService.ArtifactDelivery;
import static io.elmos.liveworkbench.LwContracts.*;
import static io.elmos.liveworkbench.ProductionContracts.*;

/** Durable read/teach/learn/catalog surfaces. Hidden graders and source bytes remain behind the host port. */
public final class ProductionLiveWorkbenchKnowledgeService {
    private final LiveWorkbenchCatalogStore catalog;
    private final LiveWorkbenchStore sessions;
    private final SandboxProviderPort provider;
    private final Clock clock;

    public ProductionLiveWorkbenchKnowledgeService(LiveWorkbenchCatalogStore catalog, LiveWorkbenchStore sessions,
                                                    SandboxProviderPort provider, Clock clock) {
        this.catalog = catalog; this.sessions = sessions; this.provider = provider; this.clock = clock;
    }

    public RuntimeProfile registerProfile(PrincipalScope scope, RuntimeProfile profile) {
        require(scope, "workbench.catalog.write");
        return catalog.registerProfile(scope.tenantId(), profile, now());
    }
    public ArtifactDelivery registerDelivery(PrincipalScope scope, ArtifactDelivery delivery) {
        require(scope, "workbench.catalog.write");
        return catalog.registerDelivery(scope.tenantId(), delivery, now());
    }
    public ArtifactDelivery delivery(PrincipalScope scope, String id) {
        require(scope, "workbench.session.read");
        return catalog.delivery(scope.tenantId(), id).orElseThrow(() -> LiveWorkbenchException.notFound("DELIVERY_NOT_FOUND"));
    }
    public SourceAnchor registerAnchor(PrincipalScope scope, String id, SourceAnchor anchor) {
        require(scope, "workbench.catalog.write");
        return catalog.registerAnchor(scope.tenantId(), id, anchor, now());
    }
    public SourceContent source(PrincipalScope scope, String anchorId) {
        require(scope, "workbench.source.read");
        SourceAnchor anchor = catalog.anchor(scope.tenantId(), anchorId).orElseThrow(() -> LiveWorkbenchException.notFound("SOURCE_ANCHOR_NOT_FOUND"));
        return provider.readSource(scope, anchor);
    }
    public EvidenceClaim registerClaim(PrincipalScope scope, EvidenceClaim claim) {
        require(scope, "workbench.catalog.write");
        return catalog.registerClaim(scope.tenantId(), claim, now());
    }
    public ExplanationView explain(PrincipalScope scope, ExplanationRequest request) {
        require(scope, "workbench.source.read");
        SourceAnchor anchor = catalog.anchor(scope.tenantId(), request.anchorId()).orElseThrow(() -> LiveWorkbenchException.notFound("SOURCE_ANCHOR_NOT_FOUND"));
        return new ExplanationView(anchor, request.audience(), request.mode(),
                catalog.claimsForAnchor(scope.tenantId(), request.anchorId()),
                List.of("Only non-stale, evidence-linked claims from the immutable snapshot are returned.",
                        "Inference is never promoted to verified static or runtime-observed evidence."));
    }
    public LearningMission registerMission(PrincipalScope scope, LearningMission mission) {
        require(scope, "workbench.catalog.write");
        return catalog.registerMission(scope.tenantId(), mission, now());
    }
    public LearningMission mission(PrincipalScope scope, String id) {
        require(scope, "workbench.learning.read");
        return catalog.mission(scope.tenantId(), id).orElseThrow(() -> LiveWorkbenchException.notFound("MISSION_NOT_FOUND"));
    }
    public SemanticCorrespondence registerCorrespondence(PrincipalScope scope, SemanticCorrespondence value) {
        require(scope, "workbench.catalog.write");
        return catalog.registerCorrespondence(scope.tenantId(), value, now());
    }
    public SemanticCorrespondence correspondence(PrincipalScope scope, String id) {
        require(scope, "workbench.source.read");
        return catalog.correspondence(scope.tenantId(), id).orElseThrow(() -> LiveWorkbenchException.notFound("CORRESPONDENCE_NOT_FOUND"));
    }
    public int invalidateSnapshot(PrincipalScope scope, String snapshotId) {
        require(scope, "workbench.catalog.write");
        if (!LwDigest.exact(snapshotId)) throw new IllegalArgumentException("snapshot digest");
        return catalog.invalidateSnapshot(scope.tenantId(), snapshotId);
    }

    public MissionAttemptReceipt attempt(PrincipalScope scope, String missionId, MissionAttemptRequest request,
                                         String idempotencyKey) {
        require(scope, "workbench.learning.attempt");
        validIdempotencyKey(idempotencyKey);
        LearningMission mission = catalog.mission(scope.tenantId(), missionId).orElseThrow(() -> LiveWorkbenchException.notFound("MISSION_NOT_FOUND"));
        if (mission.stale()) throw LiveWorkbenchException.conflict("MISSION_STALE");
        SessionView session = sessions.find(scope.tenantId(), request.sessionId()).orElseThrow(LiveWorkbenchException::notFound);
        if (!session.accountId().equals(scope.accountId()) || !session.snapshotId().equals(mission.snapshotId())
                || session.generation() != request.generation() || session.state() != SessionState.READY)
            throw LiveWorkbenchException.conflict("MISSION_SESSION_BINDING_INVALID");
        Set<String> committedEvents = new HashSet<>();
        long after = 0;
        while (committedEvents.size() < 5_000) {
            List<EventView> page = sessions.events(scope.tenantId(), session.sessionId(), after, 500);
            if (page.isEmpty()) break;
            page.forEach(event -> committedEvents.add(event.eventId()));
            after = page.getLast().sequence();
            if (page.size() < 500) break;
        }
        if (!committedEvents.containsAll(request.runtimeEventIds()))
            throw LiveWorkbenchException.conflict("ASSESSMENT_RUNTIME_EVIDENCE_NOT_COMMITTED");
        String requestDigest = LwDigest.sha256(missionId + "\n" + request.sessionId() + "\n" + request.generation()
                + "\n" + request.answersDigest() + "\n" + String.join("\n", request.runtimeEventIds()));
        LiveWorkbenchCatalogStore.AttemptReservation reservation = catalog.reserveAttempt(scope.tenantId(), scope.actorId(),
                missionId, request, UUID.randomUUID().toString(), idempotencyKey, requestDigest, now());
        MissionAttemptReceipt receipt = reservation.receipt();
        if (receipt.state() == CommandState.COMMITTED || receipt.state() == CommandState.DENIED) return receipt;
        MissionAttemptReceipt result = reservation.created()
                ? provider.assess(scope, mission, request, receipt.attemptId(), idempotencyKey)
                : provider.reconcileAssessment(scope, mission, receipt.attemptId(), idempotencyKey);
        if (!receipt.attemptId().equals(result.attemptId()) || !idempotencyKey.equals(result.idempotencyKey()))
            throw LiveWorkbenchException.unavailable("ASSESSMENT_RECEIPT_BINDING_INVALID");
        return catalog.completeAttempt(scope.tenantId(), scope.actorId(), missionId, idempotencyKey, result, now());
    }

    private static void require(PrincipalScope scope, String authority) {
        if (!scope.has(authority)) throw LiveWorkbenchException.denied("AUTHORITY_REQUIRED");
    }
    private static void validIdempotencyKey(String value) {
        if (value == null || !value.matches("[A-Za-z0-9._:-]{8,200}")) throw new IllegalArgumentException("valid Idempotency-Key required");
    }
    private long now() { return clock.instant().getEpochSecond(); }
}
