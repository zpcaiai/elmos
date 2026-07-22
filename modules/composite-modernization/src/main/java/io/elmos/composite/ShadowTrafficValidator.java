package io.elmos.composite;

import java.util.ArrayList;
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import static io.elmos.composite.CompositeModels.*;

public final class ShadowTrafficValidator {
    public enum ShadowType { HTTP_MIRROR, GRPC_MIRROR, MESSAGE_REPLAY, DATABASE_QUERY_COMPARE,
        FILE_REPLAY, MODEL_SHADOW_INFERENCE, BATCH_SHADOW_RUN }
    public enum SideEffectPolicy { SUPPRESS, STUB, REDIRECT_TO_SHADOW_STORE, TRANSACTION_ROLLBACK,
        DRY_RUN, COMPENSATE, UNSAFE_NOT_ALLOWED }
    public enum SensitiveDataAction { REDACT, TOKENIZE, HASH, SYNTHESIZE, DROP }
    public enum ComparisonMode { DETERMINISTIC, NORMALIZED, TOLERANCE, NOT_COMPARABLE }

    public record SafetyPolicy(ShadowType type, boolean writeCapable, SideEffectPolicy sideEffectPolicy,
                               Map<String,SensitiveDataAction> sensitiveFields,
                               boolean primaryCriticalPathUnaffected, boolean independentResponseCapture,
                               boolean tenantScoped, String retentionPolicyRef) {
        public SafetyPolicy {
            Objects.requireNonNull(type); Objects.requireNonNull(sideEffectPolicy);
            sensitiveFields = immutable(sensitiveFields);
        }
    }
    public record ShadowInput(String experimentId, String requestId, String tenantId,
                              String primaryRequestHash, String shadowRequestHash,
                              String transformationRef, String contractVersion,
                              List<String> evidenceRefs) {}
    public record DifferentialResult(String experimentId, String requestId, ShadowStatus status,
                                     List<String> differences, List<String> evidenceRefs,
                                     boolean primaryResultUnaffected, boolean canEnterCanary) {}
    public record ComparisonPolicy(Set<ComparisonMode> modes, Set<String> ignoredFields,
                                   Set<String> semanticFields, Map<String,Double> absoluteToleranceByField,
                                   Set<String> expectedDifferenceFields, boolean expectedDifferencesApproved) {
        public ComparisonPolicy {
            modes = Set.copyOf(modes == null || modes.isEmpty() ? Set.of(ComparisonMode.DETERMINISTIC) : modes);
            ignoredFields = Set.copyOf(ignoredFields == null ? Set.of() : ignoredFields);
            semanticFields = Set.copyOf(semanticFields == null ? Set.of() : semanticFields);
            absoluteToleranceByField = immutable(absoluteToleranceByField);
            expectedDifferenceFields = Set.copyOf(expectedDifferenceFields == null ? Set.of() : expectedDifferenceFields);
            if (modes.contains(ComparisonMode.NOT_COMPARABLE) && modes.size() != 1) {
                throw new IllegalArgumentException("NOT_COMPARABLE cannot be combined with comparable modes");
            }
            absoluteToleranceByField.forEach((field, tolerance) -> {
                if (field == null || field.isBlank() || tolerance == null || !Double.isFinite(tolerance) || tolerance < 0) {
                    throw new IllegalArgumentException("numeric tolerance must be finite and non-negative");
                }
            });
            if (!absoluteToleranceByField.isEmpty() && !modes.contains(ComparisonMode.TOLERANCE)) {
                throw new IllegalArgumentException("numeric tolerances require TOLERANCE mode");
            }
            if ((!ignoredFields.isEmpty() || !semanticFields.isEmpty()) && !modes.contains(ComparisonMode.NORMALIZED)) {
                throw new IllegalArgumentException("ignored or semantic fields require NORMALIZED mode");
            }
            if (expectedDifferencesApproved && expectedDifferenceFields.isEmpty()) {
                throw new IllegalArgumentException("approved expected differences require explicit fields");
            }
        }
    }

    public DifferentialResult compare(SafetyPolicy policy, ShadowInput input,
                                      Map<String,Object> primary, Map<String,Object> shadow,
                                      Set<String> normalizedFields, boolean shadowExecutionSucceeded,
                                      List<String> responseEvidenceRefs) {
        Set<ComparisonMode> modes = normalizedFields == null || normalizedFields.isEmpty()
                ? Set.of(ComparisonMode.DETERMINISTIC)
                : Set.of(ComparisonMode.DETERMINISTIC, ComparisonMode.NORMALIZED);
        return compare(policy, input, primary, shadow,
                new ComparisonPolicy(modes, normalizedFields, Set.of(), Map.of(), Set.of(), false),
                shadowExecutionSucceeded, responseEvidenceRefs);
    }

    public DifferentialResult compare(SafetyPolicy policy, ShadowInput input,
                                      Map<String,Object> primary, Map<String,Object> shadow,
                                      ComparisonPolicy comparisonPolicy, boolean shadowExecutionSucceeded,
                                      List<String> responseEvidenceRefs) {
        ArrayList<String> differences = new ArrayList<>();
        if (!policy.primaryCriticalPathUnaffected()) differences.add("SHADOW_ON_PRIMARY_CRITICAL_PATH");
        if (!policy.independentResponseCapture()) differences.add("SHADOW_RESPONSE_CAPTURE_MISSING");
        if (!policy.tenantScoped() || input.tenantId() == null || input.tenantId().isBlank()) differences.add("SHADOW_TENANT_SCOPE_MISSING");
        if (policy.retentionPolicyRef() == null || policy.retentionPolicyRef().isBlank()) differences.add("SHADOW_RETENTION_POLICY_MISSING");
        if (policy.writeCapable() && (policy.sideEffectPolicy() == SideEffectPolicy.UNSAFE_NOT_ALLOWED
                || policy.sideEffectPolicy() == SideEffectPolicy.COMPENSATE)) {
            differences.add("SHADOW_WRITE_SIDE_EFFECT_NOT_SAFELY_SUPPRESSED");
        }
        if (policy.sensitiveFields().values().stream().anyMatch(Objects::isNull)) differences.add("SENSITIVE_FIELD_POLICY_INCOMPLETE");
        if (!shadowExecutionSucceeded) {
            differences.add("SHADOW_EXECUTION_FAILED");
            return result(input, ShadowStatus.SHADOW_EXECUTION_FAILED, differences, responseEvidenceRefs,
                    policy.primaryCriticalPathUnaffected(), false);
        }
        if (comparisonPolicy.modes().contains(ComparisonMode.NOT_COMPARABLE)) {
            differences.add("NONDETERMINISTIC_INPUT_NOT_COMPARABLE");
            return result(input, differences.size() == 1 ? ShadowStatus.NOT_COMPARABLE : ShadowStatus.REGRESSION,
                    differences, responseEvidenceRefs, policy.primaryCriticalPathUnaffected(), false);
        }
        Map<String,Object> normalizedPrimary = normalized(primary, comparisonPolicy.ignoredFields());
        Map<String,Object> normalizedShadow = normalized(shadow, comparisonPolicy.ignoredFields());
        Set<String> keys = new java.util.TreeSet<>(); keys.addAll(normalizedPrimary.keySet()); keys.addAll(normalizedShadow.keySet());
        for (String key : keys) {
            Object primaryValue = normalizedPrimary.get(key); Object shadowValue = normalizedShadow.get(key);
            if (Objects.equals(primaryValue, shadowValue)) continue;
            if (comparisonPolicy.semanticFields().contains(key) && semanticallyEqual(primaryValue, shadowValue))
                differences.add("SEMANTIC_DIFFERENCE:" + key);
            else if (withinTolerance(primaryValue, shadowValue, comparisonPolicy.absoluteToleranceByField().get(key)))
                differences.add("WITHIN_TOLERANCE:" + key);
            else if (comparisonPolicy.expectedDifferenceFields().contains(key))
                differences.add("EXPECTED_DIFFERENCE:" + key);
            else differences.add("VALUE_DIFFERENCE:" + key);
        }
        boolean policyFailure = differences.stream().anyMatch(this::isSafetyFailure);
        boolean unexpectedDifference = differences.stream().anyMatch(value -> value.startsWith("VALUE_DIFFERENCE:"));
        ShadowStatus status = policyFailure || unexpectedDifference ? ShadowStatus.REGRESSION
                : differences.stream().anyMatch(value -> value.startsWith("EXPECTED_DIFFERENCE:")) ? ShadowStatus.EXPECTED_DIFFERENCE
                : differences.stream().anyMatch(value -> value.startsWith("WITHIN_TOLERANCE:")) ? ShadowStatus.WITHIN_TOLERANCE
                : differences.stream().anyMatch(value -> value.startsWith("SEMANTIC_DIFFERENCE:")) ? ShadowStatus.SEMANTIC_MATCH
                : ShadowStatus.EXACT_MATCH;
        boolean canary = status == ShadowStatus.EXACT_MATCH || status == ShadowStatus.SEMANTIC_MATCH
                || status == ShadowStatus.WITHIN_TOLERANCE
                || status == ShadowStatus.EXPECTED_DIFFERENCE && comparisonPolicy.expectedDifferencesApproved();
        return result(input, status, differences, responseEvidenceRefs,
                policy.primaryCriticalPathUnaffected(), canary);
    }

    private boolean isSafetyFailure(String difference) {
        return !difference.startsWith("VALUE_DIFFERENCE:")
                && !difference.startsWith("SEMANTIC_DIFFERENCE:")
                && !difference.startsWith("WITHIN_TOLERANCE:")
                && !difference.startsWith("EXPECTED_DIFFERENCE:");
    }

    private boolean semanticallyEqual(Object primary, Object shadow) {
        if (primary instanceof Number first && shadow instanceof Number second) {
            try {
                return new BigDecimal(first.toString()).compareTo(new BigDecimal(second.toString())) == 0;
            } catch (NumberFormatException ignored) {
                return false;
            }
        }
        if (primary instanceof CharSequence first && shadow instanceof CharSequence second) {
            return first.toString().strip().equalsIgnoreCase(second.toString().strip());
        }
        return false;
    }

    private boolean withinTolerance(Object primary, Object shadow, Double tolerance) {
        if (tolerance == null || !(primary instanceof Number first) || !(shadow instanceof Number second)) return false;
        return Math.abs(first.doubleValue() - second.doubleValue()) <= tolerance;
    }

    private Map<String,Object> normalized(Map<String,Object> source, Set<String> ignored) {
        LinkedHashMap<String,Object> result = new LinkedHashMap<>();
        source.entrySet().stream().filter(entry -> !ignored.contains(entry.getKey()))
                .sorted(Map.Entry.comparingByKey()).forEach(entry -> result.put(entry.getKey(), entry.getValue()));
        return result;
    }

    private DifferentialResult result(ShadowInput input, ShadowStatus status, List<String> differences,
                                      List<String> responseEvidenceRefs, boolean primaryUnaffected, boolean canary) {
        List<String> evidence = new ArrayList<>(immutable(input.evidenceRefs()));
        evidence.addAll(immutable(responseEvidenceRefs));
        if (evidence.isEmpty()) {
            differences.add("SHADOW_EVIDENCE_MISSING"); canary = false;
            if (status != ShadowStatus.SHADOW_EXECUTION_FAILED) status = ShadowStatus.NOT_COMPARABLE;
        }
        return new DifferentialResult(input.experimentId(), input.requestId(), status,
                List.copyOf(differences), evidence.stream().distinct().sorted().toList(), primaryUnaffected, canary);
    }
}
