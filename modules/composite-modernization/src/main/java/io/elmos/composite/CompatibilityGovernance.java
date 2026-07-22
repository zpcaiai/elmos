package io.elmos.composite;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import static io.elmos.composite.CompositeModels.*;

public final class CompatibilityGovernance {
    public enum WindowStatus { ACTIVE, EXPIRING, EXPIRED_WITH_USAGE, EXPIRED_UNUSED, CLOSURE_APPROVED, CLOSED }
    public enum Strategy {
        MULTI_VERSION_ENDPOINT, OPTIONAL_FIELD_EXPANSION, UNKNOWN_FIELD_TOLERANCE, UPCAST, DOWNCAST,
        SCHEMA_TRANSLATION, VERSIONED_TOPIC, DUAL_PUBLISH, COMPATIBILITY_VIEW, SDK_FACADE
    }
    public enum RuntimeType {
        API_GATEWAY_ADAPTER, HTTP_REQUEST_TRANSLATOR, HTTP_RESPONSE_TRANSLATOR, GRPC_PROXY,
        SOAP_REST_BRIDGE, MESSAGE_TRANSFORMER, EVENT_UPCASTER, EVENT_DOWNCASTER, SCHEMA_TRANSLATOR,
        SDK_FACADE, DATABASE_VIEW, DATABASE_TRIGGER_ADAPTER, FILE_FORMAT_TRANSLATOR,
        MODEL_INPUT_ADAPTER, MODEL_OUTPUT_ADAPTER, AUTH_CONTEXT_BRIDGE, SIDECAR
    }
    public enum LossPolicy { LOSSLESS, LOSSY_APPROVED, UNSUPPORTED }

    public record CompatibilityWindow(
            String windowId, String organizationId, String contractId, String oldVersion,
            String newVersion, Instant startsAt, Instant expiresAt, String owner,
            List<Strategy> strategies, List<String> supportedCombinations, long oldVersionUsage,
            boolean externalConsumersConfirmed, boolean observationWindowComplete,
            boolean rollbackWindowEnded, String removalTaskId, List<String> evidenceRefs) {
        public CompatibilityWindow {
            require(windowId, "windowId"); require(organizationId, "organizationId");
            require(contractId, "contractId"); require(oldVersion, "oldVersion"); require(newVersion, "newVersion");
            Objects.requireNonNull(startsAt, "startsAt"); Objects.requireNonNull(expiresAt, "expiresAt");
            if (!expiresAt.isAfter(startsAt)) throw new IllegalArgumentException("compatibility window expiry must follow start");
            require(owner, "owner"); strategies = immutable(strategies);
            supportedCombinations = immutable(supportedCombinations); require(removalTaskId, "removalTaskId");
            evidenceRefs = immutable(evidenceRefs);
        }
    }

    public record WindowDecision(WindowStatus status, boolean contractRemovalAllowed, List<String> blockers) {}

    public WindowDecision evaluate(CompatibilityWindow window, Instant now, boolean closureApproved) {
        Objects.requireNonNull(window); Objects.requireNonNull(now);
        ArrayList<String> blockers = new ArrayList<>();
        boolean expired = !now.isBefore(window.expiresAt());
        if (window.oldVersionUsage() > 0) blockers.add("OLD_VERSION_USAGE_PRESENT");
        if (!window.externalConsumersConfirmed()) blockers.add("EXTERNAL_CONSUMER_CONFIRMATION_MISSING");
        if (!window.observationWindowComplete()) blockers.add("OBSERVATION_WINDOW_INCOMPLETE");
        if (!window.rollbackWindowEnded()) blockers.add("ROLLBACK_WINDOW_ACTIVE");
        if (window.evidenceRefs().isEmpty()) blockers.add("USAGE_EVIDENCE_MISSING");
        WindowStatus status;
        if (expired && window.oldVersionUsage() > 0) status = WindowStatus.EXPIRED_WITH_USAGE;
        else if (expired && !blockers.isEmpty()) status = WindowStatus.EXPIRED_UNUSED;
        else if (expired && closureApproved) status = WindowStatus.CLOSURE_APPROVED;
        else if (now.isAfter(window.expiresAt().minusSeconds(7 * 24 * 3600L))) status = WindowStatus.EXPIRING;
        else status = WindowStatus.ACTIVE;
        return new WindowDecision(status, expired && closureApproved && blockers.isEmpty(), List.copyOf(blockers));
    }

    public record AdapterCandidate(
            String adapterId, RuntimeType runtimeType, String owner, Instant expiresAt,
            LossPolicy lossPolicy, boolean lossApproved, boolean deterministic,
            boolean stateless, boolean idempotent, boolean observable, boolean independentlyDeployable,
            boolean independentlyRollbackable, boolean containsBusinessLogic,
            boolean errorSemanticsVerified, boolean authenticationSemanticsVerified,
            boolean compiled, boolean contractTested, boolean propertyTested,
            boolean securityReviewed, boolean performanceTested, boolean agentGenerated,
            boolean humanApproved, List<String> evidenceRefs) {}
    public record AdapterDecision(String adapterId, String status, List<String> blockers, boolean publishAllowed) {}

    public AdapterDecision evaluate(AdapterCandidate candidate, Instant now) {
        ArrayList<String> blockers = new ArrayList<>();
        if (!candidate.expiresAt().isAfter(now)) blockers.add("ADAPTER_EXPIRY_INVALID");
        if (candidate.lossPolicy() == LossPolicy.UNSUPPORTED) blockers.add("ADAPTER_TRANSFORMATION_UNSUPPORTED");
        if (candidate.lossPolicy() == LossPolicy.LOSSY_APPROVED && !candidate.lossApproved()) blockers.add("LOSSY_APPROVAL_MISSING");
        if (!candidate.deterministic()) blockers.add("DETERMINISTIC_GENERATION_MISSING");
        if (!candidate.stateless() || !candidate.idempotent()) blockers.add("ADAPTER_STATE_OR_IDEMPOTENCY_RISK");
        if (!candidate.observable() || !candidate.independentlyDeployable() || !candidate.independentlyRollbackable()) {
            blockers.add("ADAPTER_OPERATIONAL_BOUNDARY_INCOMPLETE");
        }
        if (candidate.containsBusinessLogic()) blockers.add("ADAPTER_NEW_BUSINESS_LOGIC_FORBIDDEN");
        if (!candidate.errorSemanticsVerified()) blockers.add("ERROR_SEMANTICS_UNVERIFIED");
        if (!candidate.authenticationSemanticsVerified()) blockers.add("AUTH_SEMANTICS_UNVERIFIED");
        if (!candidate.compiled() || !candidate.contractTested() || !candidate.propertyTested()
                || !candidate.securityReviewed() || !candidate.performanceTested()) blockers.add("ADAPTER_VALIDATION_INCOMPLETE");
        if (candidate.agentGenerated() && !candidate.humanApproved()) blockers.add("AGENT_CANDIDATE_NOT_APPROVED");
        if (candidate.evidenceRefs().isEmpty()) blockers.add("ADAPTER_EVIDENCE_MISSING");
        return new AdapterDecision(candidate.adapterId(), blockers.isEmpty() ? "APPROVED" : "BLOCKED",
                List.copyOf(blockers), blockers.isEmpty());
    }
}
