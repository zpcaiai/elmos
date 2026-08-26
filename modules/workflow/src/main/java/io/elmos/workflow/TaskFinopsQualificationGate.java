package io.elmos.workflow;

import java.util.List;
import java.util.Objects;

/**
 * Fail-closed local composition of qualification checks.
 *
 * <p>The gate distinguishes a local contract result from external
 * certification. Missing runtime evidence can only produce
 * {@code READY_FOR_EXTERNAL_GATE}; it can never produce a certified result.
 * The class has no signing key, provider client, database connection, or
 * release authority.</p>
 */
public final class TaskFinopsQualificationGate {
    public static final String EXTERNAL_EVIDENCE_NOT_RUN = "NOT_RUN";
    public static final String PRODUCTION_CERTIFICATION = "NOT_CERTIFIED";

    public enum CheckStatus {
        PASS,
        FAIL,
        BLOCKED,
        NOT_RUN,
        UNKNOWN
    }

    public enum Decision {
        BLOCKED,
        READY_FOR_EXTERNAL_GATE
    }

    public record Check(String name, CheckStatus status, String detail) {
        public Check {
            if (name == null || name.isBlank() || detail == null || detail.isBlank()) {
                throw new IllegalArgumentException("ELMOS_MTF_QUALIFICATION_CHECK_INVALID");
            }
            Objects.requireNonNull(status, "status");
        }
    }

    public record GateRequest(
            List<Check> checks,
            String externalEvidenceStatus,
            String productionCertification
    ) {
        public GateRequest {
            checks = List.copyOf(Objects.requireNonNull(checks, "checks"));
            if (checks.isEmpty() || !EXTERNAL_EVIDENCE_NOT_RUN.equals(externalEvidenceStatus)
                    || !PRODUCTION_CERTIFICATION.equals(productionCertification)) {
                throw new IllegalArgumentException("ELMOS_MTF_QUALIFICATION_REQUEST_INVALID");
            }
        }
    }

    public record GateResult(
            Decision decision,
            String reason,
            String externalEvidenceStatus,
            String productionCertification
    ) {
        public GateResult {
            Objects.requireNonNull(decision, "decision");
            if (reason == null || reason.isBlank()
                    || !EXTERNAL_EVIDENCE_NOT_RUN.equals(externalEvidenceStatus)
                    || !PRODUCTION_CERTIFICATION.equals(productionCertification)) {
                throw new IllegalArgumentException("ELMOS_MTF_QUALIFICATION_RESULT_INVALID");
            }
        }
    }

    private TaskFinopsQualificationGate() {}

    /**
     * Produces the strongest safe local decision while preserving the
     * external evidence and production certification boundary.
     */
    public static GateResult evaluate(GateRequest request) {
        Objects.requireNonNull(request, "request");
        for (Check check : request.checks()) {
            if (check.status() != CheckStatus.PASS) {
                return new GateResult(
                        Decision.BLOCKED,
                        "CHECK_NOT_PASS:" + check.name(),
                        EXTERNAL_EVIDENCE_NOT_RUN,
                        PRODUCTION_CERTIFICATION);
            }
        }
        return new GateResult(
                Decision.READY_FOR_EXTERNAL_GATE,
                "LOCAL_CHECKS_PASS_EXTERNAL_EVIDENCE_REQUIRED",
                EXTERNAL_EVIDENCE_NOT_RUN,
                PRODUCTION_CERTIFICATION);
    }
}
