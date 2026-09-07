package io.elmos.commercial;

import io.elmos.commercial.CommercialModels.*;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;

public final class SlaAndSupportService {

    public ServiceLevelDecision evaluate(ServiceLevelObjective objective, ServiceLevelMeasurement measurement,
                                         boolean exclusionContractuallyAllowed, BigDecimal creditRate,
                                         BigDecimal maximumCredit) {
        if (!objective.objectiveId().equals(measurement.objectiveId())) throw new IllegalArgumentException("SLO_MEASUREMENT_MISMATCH");
        List<String> reasons = new ArrayList<>();
        BigDecimal effective = measurement.achieved();
        if (measurement.excluded().signum() > 0) {
            if (!exclusionContractuallyAllowed || measurement.exclusionEvidenceRef() == null
                    || measurement.exclusionEvidenceRef().isBlank()) {
                reasons.add("EXCLUSION_REJECTED_NO_CONTRACT_OR_EVIDENCE");
            } else {
                effective = effective.add(measurement.excluded());
                reasons.add("EVIDENCED_EXCLUSION_APPLIED");
            }
        }
        boolean breached = effective.compareTo(objective.target()) < 0;
        BigDecimal credit = BigDecimal.ZERO;
        if (breached) {
            BigDecimal shortfall = objective.target().subtract(effective).max(BigDecimal.ZERO);
            credit = shortfall.multiply(creditRate).setScale(2, RoundingMode.HALF_UP).min(maximumCredit);
            reasons.add("SLA_BREACH_CONFIRMED");
        }
        return new ServiceLevelDecision(breached, credit, reasons,
                breached ? "INVOICE_ADJUSTMENT_REQUEST_REQUIRED" : "NOT_REQUIRED");
    }

    public SupportTicket triage(String ticketId, String type, TicketContext context,
                                boolean multiCustomerOutage, boolean evidenceIntegrityRisk,
                                boolean suspectedDataExposure, boolean enterpriseCriticalBlock,
                                boolean workaroundAvailable, String impact, String urgency,
                                List<String> fingerprints) {
        SupportSeverity severity;
        if (multiCustomerOutage || evidenceIntegrityRisk || suspectedDataExposure) severity = SupportSeverity.SEV1;
        else if (enterpriseCriticalBlock) severity = SupportSeverity.SEV2;
        else if (!workaroundAvailable) severity = SupportSeverity.SEV3;
        else severity = SupportSeverity.SEV4;
        String commander = severity == SupportSeverity.SEV1 ? "INCIDENT_COMMANDER_REQUIRED" : null;
        return new SupportTicket(ticketId, type, severity, TicketStatus.TRIAGED, context, impact, urgency,
                commander, severity != SupportSeverity.SEV1 && severity != SupportSeverity.SEV2, fingerprints);
    }

    public void authorizeSupportAccess(SupportTicket ticket, String organizationId, boolean customerAuthorized,
                                       boolean scopeDefined, boolean timeLimited, boolean sourceReadRequested) {
        if (!ticket.context().organizationId().equals(organizationId)) throw new SecurityException("CROSS_TENANT_SUPPORT_ACCESS");
        if (!customerAuthorized || !scopeDefined || !timeLimited) throw new SecurityException("SUPPORT_GRANT_REQUIRED");
        if (sourceReadRequested && !"SOURCE_READ_APPROVED".equals(ticket.impact())) {
            throw new SecurityException("SOURCE_ACCESS_NOT_AUTHORIZED_BY_TICKET");
        }
    }

    public boolean requiresProblemRecord(List<SupportTicket> tickets, String fingerprint) {
        return tickets.stream().filter(ticket -> ticket.relatedFingerprints().contains(fingerprint)).count() >= 2;
    }
}
