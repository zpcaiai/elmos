package io.elmos.liveworkbench;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.Optional;
import java.util.function.Supplier;

import static io.elmos.liveworkbench.LiveWorkbenchService.ArtifactDelivery;
import static io.elmos.liveworkbench.LwContracts.*;
import static io.elmos.liveworkbench.ProductionContracts.*;

public final class JdbcLiveWorkbenchCatalogStore implements LiveWorkbenchCatalogStore {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final ObjectMapper json;

    public JdbcLiveWorkbenchCatalogStore(JdbcTemplate jdbc, TransactionTemplate transactions, ObjectMapper json) {
        this.jdbc = jdbc; this.transactions = transactions; this.json = json;
    }

    @Override public RuntimeProfile registerProfile(String tenantId, RuntimeProfile profile, long now) {
        return tenant(tenantId, () -> {
            String payload = encode(profile), digest = LwDigest.sha256(payload);
            int changed = jdbc.update("""
                    INSERT INTO lw_runtime_profiles(tenant_id,profile_id,qualification,runtime_digest,payload,payload_digest,created_at_epoch)
                    VALUES (?,?,?,?,CAST(? AS jsonb),?,?) ON CONFLICT (tenant_id,profile_id) DO NOTHING
                    """, tenantId, profile.profileId(), profile.qualification().name(), profile.runtimeDigest(), payload, digest, now);
            if (changed == 0) exact("lw_runtime_profiles", "profile_id", tenantId, profile.profileId(), digest);
            return profile;
        });
    }

    @Override public Optional<RuntimeProfile> profile(String tenantId, String profileId) {
        return tenant(tenantId, () -> one("SELECT payload::text FROM lw_runtime_profiles WHERE tenant_id=? AND profile_id=?",
                RuntimeProfile.class, tenantId, profileId));
    }

    @Override public ArtifactDelivery registerDelivery(String tenantId, ArtifactDelivery delivery, long now) {
        if (!tenantId.equals(delivery.tenantId())) throw LiveWorkbenchException.denied("DELIVERY_TENANT_MISMATCH");
        return tenant(tenantId, () -> {
            String payload = encode(delivery), digest = LwDigest.sha256(payload);
            int changed = jdbc.update("""
                    INSERT INTO lw_deliveries(tenant_id,delivery_id,repository_id,snapshot_id,runtime_profile_id,build_artifact_digest,payload,payload_digest,created_at_epoch)
                    VALUES (?,?,?,?,?,?,CAST(? AS jsonb),?,?) ON CONFLICT (tenant_id,delivery_id) DO NOTHING
                    """, tenantId, delivery.deliveryId(), delivery.repositoryId(), delivery.snapshotId(), delivery.runtimeProfileId(),
                    delivery.buildArtifactDigest(), payload, digest, now);
            if (changed == 0) exact("lw_deliveries", "delivery_id", tenantId, delivery.deliveryId(), digest);
            return delivery;
        });
    }

    @Override public Optional<ArtifactDelivery> delivery(String tenantId, String deliveryId) {
        return tenant(tenantId, () -> one("SELECT payload::text FROM lw_deliveries WHERE tenant_id=? AND delivery_id=?",
                ArtifactDelivery.class, tenantId, deliveryId));
    }

    @Override public SourceAnchor registerAnchor(String tenantId, String anchorId, SourceAnchor anchor, long now) {
        if (!tenantId.equals(anchor.tenantId())) throw LiveWorkbenchException.denied("ANCHOR_TENANT_MISMATCH");
        return tenant(tenantId, () -> {
            String payload = encode(anchor), digest = LwDigest.sha256(payload);
            int changed = jdbc.update("""
                    INSERT INTO lw_source_anchors(tenant_id,anchor_id,repository_id,snapshot_id,path,blob_digest,byte_start,byte_end,payload,payload_digest,created_at_epoch)
                    VALUES (?,?,?,?,?,?,?,?,CAST(? AS jsonb),?,?) ON CONFLICT (tenant_id,anchor_id) DO NOTHING
                    """, tenantId, anchorId, anchor.repositoryId(), anchor.snapshotId(), anchor.path(), anchor.blobDigest(),
                    anchor.byteStart(), anchor.byteEnd(), payload, digest, now);
            if (changed == 0) exact("lw_source_anchors", "anchor_id", tenantId, anchorId, digest);
            return anchor;
        });
    }

    @Override public Optional<SourceAnchor> anchor(String tenantId, String anchorId) {
        return tenant(tenantId, () -> one("SELECT payload::text FROM lw_source_anchors WHERE tenant_id=? AND anchor_id=?",
                SourceAnchor.class, tenantId, anchorId));
    }

    @Override public EvidenceClaim registerClaim(String tenantId, EvidenceClaim claim, long now) {
        if (!tenantId.equals(claim.tenantId())) throw LiveWorkbenchException.denied("CLAIM_TENANT_MISMATCH");
        return tenant(tenantId, () -> {
            String payload = encode(claim), digest = LwDigest.sha256(payload);
            int changed = jdbc.update("""
                    INSERT INTO lw_claims(tenant_id,claim_id,repository_id,snapshot_id,classification,payload,payload_digest,created_at_epoch)
                    VALUES (?,?,?,?,?,CAST(? AS jsonb),?,?) ON CONFLICT (tenant_id,claim_id) DO NOTHING
                    """, tenantId, claim.claimId(), claim.repositoryId(), claim.snapshotId(), claim.classification().name(), payload, digest, now);
            if (changed == 0) exact("lw_claims", "claim_id", tenantId, claim.claimId(), digest);
            if (changed == 1) {
                claim.sourceAnchorIds().forEach(id -> evidence(tenantId, claim.claimId(), "SOURCE_ANCHOR", id));
                claim.runtimeEventIds().forEach(id -> evidence(tenantId, claim.claimId(), "RUNTIME_EVENT", id));
            }
            return claim;
        });
    }

    @Override public List<EvidenceClaim> claimsForAnchor(String tenantId, String anchorId) {
        return tenant(tenantId, () -> jdbc.query("""
                SELECT c.payload::text FROM lw_claims c JOIN lw_claim_evidence e
                  ON e.tenant_id=c.tenant_id AND e.claim_id=c.claim_id
                WHERE c.tenant_id=? AND e.evidence_kind='SOURCE_ANCHOR' AND e.evidence_id=? AND c.stale=FALSE
                ORDER BY c.claim_id
                """, (rs, row) -> decode(rs.getString(1), EvidenceClaim.class), tenantId, anchorId));
    }

    @Override public LearningMission registerMission(String tenantId, LearningMission mission, long now) {
        if (!tenantId.equals(mission.tenantId())) throw LiveWorkbenchException.denied("MISSION_TENANT_MISMATCH");
        return tenant(tenantId, () -> {
            String payload = encode(mission), digest = LwDigest.sha256(payload);
            int changed = jdbc.update("""
                    INSERT INTO lw_missions(tenant_id,mission_id,repository_id,snapshot_id,payload,payload_digest,stale,created_at_epoch)
                    VALUES (?,?,?,?,CAST(? AS jsonb),?,?,?) ON CONFLICT (tenant_id,mission_id) DO NOTHING
                    """, tenantId, mission.missionId(), mission.repositoryId(), mission.snapshotId(), payload, digest, mission.stale(), now);
            if (changed == 0) exact("lw_missions", "mission_id", tenantId, mission.missionId(), digest);
            return mission;
        });
    }

    @Override public Optional<LearningMission> mission(String tenantId, String missionId) {
        return tenant(tenantId, () -> jdbc.query("SELECT payload::text,stale FROM lw_missions WHERE tenant_id=? AND mission_id=?",
                (rs, row) -> {
                    LearningMission value = decode(rs.getString(1), LearningMission.class);
                    return rs.getBoolean(2) && !value.stale() ? stale(value) : value;
                }, tenantId, missionId).stream().findFirst());
    }

    @Override public SemanticCorrespondence registerCorrespondence(String tenantId, SemanticCorrespondence value, long now) {
        if (!tenantId.equals(value.tenantId())) throw LiveWorkbenchException.denied("CORRESPONDENCE_TENANT_MISMATCH");
        return tenant(tenantId, () -> {
            String payload = encode(value), digest = LwDigest.sha256(payload);
            int changed = jdbc.update("""
                    INSERT INTO lw_correspondences(tenant_id,mapping_id,source_snapshot_id,target_snapshot_id,payload,payload_digest,created_at_epoch)
                    VALUES (?,?,?,?,CAST(? AS jsonb),?,?) ON CONFLICT (tenant_id,mapping_id) DO NOTHING
                    """, tenantId, value.mappingId(), value.sourceSnapshotId(), value.targetSnapshotId(), payload, digest, now);
            if (changed == 0) exact("lw_correspondences", "mapping_id", tenantId, value.mappingId(), digest);
            return value;
        });
    }

    @Override public Optional<SemanticCorrespondence> correspondence(String tenantId, String mappingId) {
        return tenant(tenantId, () -> one("SELECT payload::text FROM lw_correspondences WHERE tenant_id=? AND mapping_id=?",
                SemanticCorrespondence.class, tenantId, mappingId));
    }

    @Override public AttemptReservation reserveAttempt(String tenantId, String actorId, String missionId,
                                                        MissionAttemptRequest request, String attemptId,
                                                        String idempotencyKey, String requestDigest, long now) {
        return tenant(tenantId, () -> {
            List<MissionAttemptReceipt> prior = jdbc.query("""
                    SELECT attempt_id,idempotency_key,state,receipt::text,version FROM lw_attempts
                    WHERE tenant_id=? AND mission_id=? AND actor_id=? AND idempotency_key=?
                    """, (rs, row) -> attempt(rs.getString(1), rs.getString(2), rs.getString(3), rs.getString(4), rs.getLong(5)),
                    tenantId, missionId, actorId, idempotencyKey);
            if (!prior.isEmpty()) {
                String stored = jdbc.queryForObject("SELECT request_digest FROM lw_attempts WHERE tenant_id=? AND mission_id=? AND actor_id=? AND idempotency_key=?",
                        String.class, tenantId, missionId, actorId, idempotencyKey);
                if (!requestDigest.equals(stored)) throw LiveWorkbenchException.conflict("IDEMPOTENCY_PAYLOAD_CONFLICT");
                return new AttemptReservation(prior.getFirst(), false);
            }
            jdbc.update("""
                    INSERT INTO lw_attempts(tenant_id,mission_id,attempt_id,actor_id,session_id,idempotency_key,request_digest,state,created_at_epoch)
                    VALUES (?,?,?,?,?,?,?,'PENDING',?)
                    """, tenantId, missionId, attemptId, actorId, request.sessionId(), idempotencyKey, requestDigest, now);
            return new AttemptReservation(new MissionAttemptReceipt(attemptId, idempotencyKey, CommandState.PENDING,
                    null, List.of(), List.of(), 0), true);
        });
    }

    @Override public MissionAttemptReceipt completeAttempt(String tenantId, String actorId, String missionId, String idempotencyKey,
                                                            MissionAttemptReceipt receipt, long now) {
        return tenant(tenantId, () -> {
            int changed = jdbc.update("""
                    UPDATE lw_attempts SET state=?,receipt=CAST(? AS jsonb),completed_at_epoch=?,version=version+1
                    WHERE tenant_id=? AND actor_id=? AND mission_id=? AND idempotency_key=? AND state IN ('PENDING','UNKNOWN')
                    """, receipt.state().name(), encode(receipt), now, tenantId, actorId, missionId, idempotencyKey);
            if (changed != 1) {
                return jdbc.query("SELECT attempt_id,idempotency_key,state,receipt::text,version FROM lw_attempts WHERE tenant_id=? AND actor_id=? AND mission_id=? AND idempotency_key=?",
                        (rs, row) -> attempt(rs.getString(1), rs.getString(2), rs.getString(3), rs.getString(4), rs.getLong(5)),
                        tenantId, actorId, missionId, idempotencyKey).stream().findFirst()
                        .orElseThrow(() -> LiveWorkbenchException.notFound("ATTEMPT_NOT_FOUND"));
            }
            return new MissionAttemptReceipt(receipt.attemptId(), receipt.idempotencyKey(), receipt.state(), receipt.score(),
                    receipt.feedbackClaimIds(), receipt.evidenceRefs(), receipt.version() + 1);
        });
    }

    @Override public int invalidateSnapshot(String tenantId, String snapshotId) {
        return tenant(tenantId, () -> jdbc.update("UPDATE lw_missions SET stale=TRUE WHERE tenant_id=? AND snapshot_id=? AND stale=FALSE",
                tenantId, snapshotId) + jdbc.update("UPDATE lw_claims SET stale=TRUE WHERE tenant_id=? AND snapshot_id=? AND stale=FALSE",
                tenantId, snapshotId));
    }

    private void evidence(String tenantId, String claimId, String kind, String id) {
        jdbc.update("INSERT INTO lw_claim_evidence(tenant_id,claim_id,evidence_kind,evidence_id) VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                tenantId, claimId, kind, id);
    }
    private void exact(String table, String idColumn, String tenantId, String id, String digest) {
        String stored = jdbc.queryForObject("SELECT payload_digest FROM " + table + " WHERE tenant_id=? AND " + idColumn + "=?",
                String.class, tenantId, id);
        if (!digest.equals(stored)) throw LiveWorkbenchException.conflict("IMMUTABLE_CATALOG_ID_CONFLICT");
    }
    private <T> Optional<T> one(String sql, Class<T> type, Object... arguments) {
        return jdbc.query(sql, (rs, row) -> decode(rs.getString(1), type), arguments).stream().findFirst();
    }
    private MissionAttemptReceipt attempt(String attemptId, String idempotencyKey, String state, String payload, long version) {
        if (payload == null) return new MissionAttemptReceipt(attemptId, idempotencyKey, CommandState.valueOf(state),
                null, List.of(), List.of(), version);
        MissionAttemptReceipt stored = decode(payload, MissionAttemptReceipt.class);
        return new MissionAttemptReceipt(stored.attemptId(), stored.idempotencyKey(), stored.state(), stored.score(),
                stored.feedbackClaimIds(), stored.evidenceRefs(), version);
    }
    private String encode(Object value) {
        try { return json.writeValueAsString(value); }
        catch (JsonProcessingException error) { throw new IllegalArgumentException("catalog JSON invalid", error); }
    }
    private <T> T decode(String value, Class<T> type) {
        try { return json.readValue(value, type); }
        catch (JsonProcessingException error) { throw new IllegalStateException("stored catalog JSON invalid", error); }
    }
    private <T> T tenant(String tenantId, Supplier<T> operation) {
        return transactions.execute(status -> {
            jdbc.queryForObject("SELECT set_config('elmos.tenant_id', ?, true)", String.class, tenantId);
            jdbc.queryForObject("SELECT set_config('elmos.system_worker', 'false', true)", String.class);
            return operation.get();
        });
    }
    private static LearningMission stale(LearningMission mission) {
        return new LearningMission(mission.missionId(), mission.tenantId(), mission.repositoryId(), mission.snapshotId(),
                mission.title(), mission.mode(), mission.difficulty(), mission.prerequisites(), mission.sourceAnchorIds(),
                mission.steps(), mission.assessmentServiceRef(), true);
    }
}
