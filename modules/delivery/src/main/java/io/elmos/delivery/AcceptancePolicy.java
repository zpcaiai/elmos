package io.elmos.delivery;

import io.elmos.delivery.DeliveryModels.*;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public final class AcceptancePolicy {
    public AcceptancePackage evaluate(String migrationId, String deliveredHeadSha, String currentHeadSha,
                                      List<AcceptanceCriterion> criteria, List<String> conditions,
                                      boolean merged, boolean released, boolean closureRequested,
                                      String acceptedBy, Instant acceptedAt) {
        List<String> blockers = new ArrayList<>();
        if (!deliveredHeadSha.equals(currentHeadSha)) blockers.add("ACCEPTANCE_HEAD_STALE");
        criteria.stream().filter(AcceptanceCriterion::required).filter(value -> !value.satisfied())
                .forEach(value -> blockers.add("ACCEPTANCE_CRITERION_UNSATISFIED:" + value.criterionId()));
        criteria.stream().filter(value -> value.satisfied() && (value.evidenceRef() == null || value.evidenceRef().isBlank()))
                .forEach(value -> blockers.add("ACCEPTANCE_EVIDENCE_MISSING:" + value.criterionId()));
        boolean humanAccepted = acceptedBy != null && !acceptedBy.isBlank() && acceptedAt != null;
        AcceptanceStatus status;
        if (!blockers.isEmpty()) status = AcceptanceStatus.NOT_READY;
        else if (!humanAccepted) status = AcceptanceStatus.READY_FOR_ACCEPTANCE;
        else if (!conditions.isEmpty()) status = AcceptanceStatus.CONDITIONALLY_ACCEPTED;
        else status = AcceptanceStatus.ACCEPTED;
        DeliveryLifecycle lifecycle = status == AcceptanceStatus.ACCEPTED || status == AcceptanceStatus.CONDITIONALLY_ACCEPTED
                ? merged ? released ? DeliveryLifecycle.RELEASED : DeliveryLifecycle.MERGED
                : DeliveryLifecycle.ACCEPTED : DeliveryLifecycle.DELIVERED;
        if (closureRequested) {
            if (!conditions.isEmpty()) blockers.add("CONDITIONAL_ACCEPTANCE_OPEN");
            if (!merged || !released || status != AcceptanceStatus.ACCEPTED) blockers.add("CLOSURE_PREREQUISITES_NOT_MET");
            if (blockers.isEmpty()) lifecycle = DeliveryLifecycle.CLOSED;
        }
        String id = DeliveryReadModel.hash(migrationId + "\n" + deliveredHeadSha + "\n" + criteria).substring(0, 24);
        return new AcceptancePackage("acceptance-" + id, migrationId, deliveredHeadSha, currentHeadSha, status,
                lifecycle, criteria, conditions, acceptedBy, acceptedAt, blockers);
    }
}
