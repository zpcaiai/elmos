package io.elmos.delivery;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import io.elmos.delivery.DeliveryModels.*;
import io.elmos.validation.ValidationModels.Status;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;

public final class DeliveryReadModel {
    private final ObjectMapper json;
    public DeliveryReadModel(ObjectMapper json) { this.json = Objects.requireNonNull(json).copy().findAndRegisterModules(); }

    public DeliverySnapshot assemble(String migrationId, String sourceSnapshotId, String sourceCommit,
                                     String headSha, String validationDecisionId, Status validationStatus,
                                     List<EvidenceFact> facts, List<RiskItem> risks, String rollbackPlanId,
                                     String evidencePackId, Instant at) {
        List<String> blockers = new ArrayList<>();
        if (validationDecisionId == null || validationDecisionId.isBlank() || validationStatus == null)
            blockers.add("VALIDATION_DECISION_MISSING");
        else if (validationStatus == Status.FAIL || validationStatus == Status.MISSING || validationStatus == Status.INCONCLUSIVE)
            blockers.add("VALIDATION_NOT_PASSED");
        if (facts.isEmpty()) blockers.add("DELIVERY_EVIDENCE_FACTS_MISSING");
        if (facts.stream().anyMatch(fact -> fact.evidenceRefs().isEmpty())) blockers.add("DELIVERY_EVIDENCE_REFERENCE_MISSING");
        if (rollbackPlanId == null || rollbackPlanId.isBlank()) blockers.add("ROLLBACK_PLAN_MISSING");
        if (evidencePackId == null || evidencePackId.isBlank()) blockers.add("EVIDENCE_PACK_MISSING");
        risks.stream().filter(risk -> risk.blocks(at)).forEach(risk -> blockers.add("CRITICAL_RISK_OPEN:" + risk.riskId()));
        Set<String> factIds = new HashSet<>();
        if (facts.stream().anyMatch(fact -> !factIds.add(fact.factId()))) blockers.add("DUPLICATE_EVIDENCE_FACT");
        SnapshotStatus status = blockers.isEmpty()
                ? validationStatus == Status.PASS_WITH_WARNINGS || risks.stream().anyMatch(risk -> risk.status() == RiskStatus.OPEN)
                ? SnapshotStatus.READY_WITH_WARNINGS : SnapshotStatus.READY
                : blockers.stream().allMatch(value -> value.contains("MISSING")) ? SnapshotStatus.INCOMPLETE : SnapshotStatus.BLOCKED;
        Map<String,Object> canonical = new TreeMap<>();
        canonical.put("migrationId", migrationId); canonical.put("sourceSnapshotId", sourceSnapshotId);
        canonical.put("sourceCommit", sourceCommit); canonical.put("headSha", headSha);
        canonical.put("validationDecisionId", validationDecisionId); canonical.put("validationStatus", validationStatus);
        canonical.put("facts", facts.stream().sorted(Comparator.comparing(EvidenceFact::factId)).toList());
        canonical.put("risks", risks.stream().sorted(Comparator.comparing(RiskItem::riskId)).toList());
        canonical.put("rollbackPlanId", rollbackPlanId); canonical.put("evidencePackId", evidencePackId);
        canonical.put("status", status); canonical.put("blockingReasons", blockers); canonical.put("createdAt", at.toString());
        String contentHash = hash(write(canonical));
        return new DeliverySnapshot("1.0", "delivery-" + contentHash.substring(0, 24), migrationId, sourceSnapshotId,
                sourceCommit, headSha, validationDecisionId, validationStatus, facts, risks, rollbackPlanId,
                evidencePackId, status, blockers, contentHash, at);
    }

    public DeliverySnapshot markStale(DeliverySnapshot snapshot, String currentHeadSha) {
        if (snapshot.deliveryHeadSha().equals(currentHeadSha)) return snapshot;
        List<String> blockers = new ArrayList<>(snapshot.blockingReasons()); blockers.add("DELIVERY_HEAD_CHANGED");
        return new DeliverySnapshot(snapshot.schemaVersion(), snapshot.snapshotId(), snapshot.migrationId(),
                snapshot.sourceSnapshotId(), snapshot.sourceCommit(), snapshot.deliveryHeadSha(), snapshot.validationDecisionId(),
                snapshot.validationStatus(), snapshot.facts(), snapshot.risks(), snapshot.rollbackPlanId(), snapshot.evidencePackId(),
                SnapshotStatus.STALE, blockers, snapshot.contentHash(), snapshot.createdAt());
    }

    String write(Object value) {
        try { return json.writer().with(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS).writeValueAsString(value); }
        catch (Exception error) { throw new IllegalStateException("delivery serialization failed", error); }
    }
    static String hash(String value) { return hash(value.getBytes(StandardCharsets.UTF_8)); }
    static String hash(byte[] value) { try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value)); } catch (Exception error) { throw new IllegalStateException(error); } }
}
