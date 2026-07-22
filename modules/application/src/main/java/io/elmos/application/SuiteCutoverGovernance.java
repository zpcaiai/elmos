package io.elmos.application;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Independent suite judge; Workers may submit evidence but cannot mutate this decision. */
public final class SuiteCutoverGovernance {
    public enum Decision { PASS, FAIL, STALE, UNKNOWN }
    public record Evidence(String sourceArtifact, String evaluatedArtifact, boolean evidenceFresh,
                           Set<String> satisfiedGates, List<String> evidenceRefs) {
        public Evidence {
            satisfiedGates = satisfiedGates == null ? Set.of() : Set.copyOf(satisfiedGates);
            evidenceRefs = evidenceRefs == null ? List.of() : List.copyOf(evidenceRefs);
        }
    }
    public record Result(Decision decision, List<String> blockers, List<String> unknowns, Instant decidedAt) {}

    private static final Map<String, String> CUTOVER_GATES = gates(
            "CONFIGURATION_VALIDATED", "SUITE_CONFIGURATION_NOT_VALIDATED",
            "MASTER_DATA_READY", "MASTER_DATA_UNRESOLVED",
            "OPEN_TRANSACTIONS_RECONCILED", "DATA_RECONCILIATION_FAILED",
            "FINANCIAL_RECONCILED", "FINANCIAL_BALANCE_FAILED",
            "INVENTORY_RECONCILED", "INVENTORY_RECONCILIATION_FAILED",
            "PROCESS_EQUIVALENT", "PROCESS_EQUIVALENCE_FAILED",
            "STANDARDIZATION_DIFFERENCES_APPROVED", "STANDARDIZATION_APPROVAL_MISSING",
            "ROLE_MAPPING_VALIDATED", "ROLE_MAPPING_FAILED",
            "SOD_CLEAR", "SOD_CONFLICT",
            "REPORT_SECURITY_VALIDATED", "REPORT_SECURITY_FAILED",
            "INTEGRATIONS_READY", "SUITE_INTEGRATION_NOT_READY",
            "BATCH_READY", "SUITE_BATCH_NOT_READY",
            "SHARED_MASTER_AUTHORITY_READY", "MASTER_DATA_AUTHORITY_UNRESOLVED",
            "ROLLBACK_FEASIBLE", "ROLLBACK_BLOCKED",
            "POINT_OF_NO_RETURN_APPROVED", "POINT_OF_NO_RETURN_NOT_APPROVED",
            "BUSINESS_OWNER_APPROVED", "BUSINESS_OWNER_APPROVAL_MISSING");
    private static final Map<String, String> DECOMMISSION_GATES = gates(
            "STABILITY_HOLD_SATISFIED", "STABILITY_HOLD_INCOMPLETE",
            "LEGACY_USERS_ZERO", "LEGACY_USER_REMAINS",
            "LEGACY_INTERFACES_ZERO", "LEGACY_INTERFACE_REMAINS",
            "LEGACY_BATCH_ZERO", "LEGACY_BATCH_REMAINS",
            "LEGACY_REPORTS_MIGRATED", "LEGACY_REPORT_REMAINS",
            "LEGACY_OPEN_TRANSACTIONS_ZERO", "LEGACY_OPEN_TRANSACTION_REMAINS",
            "AUDIT_HISTORY_ACCESSIBLE", "AUDIT_HISTORY_NOT_ACCESSIBLE",
            "ARCHIVE_COMPLETE", "SUITE_ARCHIVE_INCOMPLETE",
            "IDENTITIES_REVOKED", "SUITE_IDENTITY_REMAINS",
            "CREDENTIALS_REVOKED", "SUITE_CREDENTIAL_REMAINS",
            "LICENSE_HANDLED", "SUITE_LICENSE_NOT_HANDLED",
            "LEGAL_HOLD_CHECKED", "LEGAL_HOLD_NOT_CHECKED");

    public Result evaluateCutover(Evidence evidence, Instant now) {
        Objects.requireNonNull(evidence, "suite cutover evidence is required");
        List<String> blockers = new ArrayList<>();
        List<String> unknowns = new ArrayList<>();
        if (!evidence.evidenceFresh() || !same(evidence.sourceArtifact(), evidence.evaluatedArtifact())) {
            blockers.add("SUITE_EVIDENCE_STALE");
        }
        missing(evidence, CUTOVER_GATES, blockers);
        if (evidence.evidenceRefs().isEmpty()) unknowns.add("SUITE_EVIDENCE_MISSING");
        return result(blockers, unknowns, now);
    }

    public Result evaluateDecommission(Evidence evidence, Instant now) {
        Result cutover = evaluateCutover(evidence, now);
        List<String> blockers = new ArrayList<>(cutover.blockers());
        List<String> unknowns = new ArrayList<>(cutover.unknowns());
        missing(evidence, DECOMMISSION_GATES, blockers);
        return result(blockers, unknowns, now);
    }

    public static Set<String> cutoverGateNames() { return CUTOVER_GATES.keySet(); }
    public static Set<String> decommissionGateNames() { return DECOMMISSION_GATES.keySet(); }

    private static void missing(Evidence evidence, Map<String, String> gates, List<String> blockers) {
        gates.forEach((gate, blocker) -> { if (!evidence.satisfiedGates().contains(gate)) blockers.add(blocker); });
    }
    private static Result result(List<String> blockers, List<String> unknowns, Instant now) {
        Decision decision = blockers.contains("SUITE_EVIDENCE_STALE") ? Decision.STALE
                : !blockers.isEmpty() ? Decision.FAIL : !unknowns.isEmpty() ? Decision.UNKNOWN : Decision.PASS;
        return new Result(decision, List.copyOf(blockers), List.copyOf(unknowns), now);
    }
    private static Map<String, String> gates(String... pairs) {
        Map<String, String> result = new LinkedHashMap<>();
        for (int index = 0; index < pairs.length; index += 2) result.put(pairs[index], pairs[index + 1]);
        return Map.copyOf(result);
    }
    private static boolean same(String left, String right) {
        return left != null && !left.isBlank() && left.equals(right);
    }
}
