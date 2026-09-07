package io.elmos.product.policy;

import java.time.Instant;
import java.util.List;
import java.util.Objects;

/** Product Batch 38 PAP/PIP/PDP/PEP contracts. */
public final class ContinuousAuthorizationModels {
    private ContinuousAuthorizationModels() {}
    public enum PolicyLanguage { REGO_V1, CEDAR_4_5, CEL }
    public enum PolicyDecision { ALLOW, DENY, ALLOW_WITH_OBLIGATIONS, REQUIRE_STEP_UP, REQUIRE_APPROVAL, QUARANTINE, DEFER, INDETERMINATE, NOT_APPLICABLE }
    public enum Readiness { BLOCKED, READY_FOR_ENFORCEMENT_GATE }

    public record DecisionRequest(
            String organizationId, String principal, String action, String resource, String environment,
            String contextSnapshotDigest, String artifactDigest, String policyId, String policyVersion,
            String bundleRevision, String bundleDigest, String engineVersion, PolicyLanguage language,
            Instant decisionTime, Instant decisionExpiresAt, PolicyDecision evaluatedDecision,
            List<String> obligations, List<String> supportedObligations, List<String> determiningPolicies,
            boolean contextComplete, boolean contextFresh, boolean factsTrusted, boolean factsConflicted,
            boolean bundleSigned, boolean bundleRevoked, boolean bundleExpired, boolean languageTypeChecked,
            boolean positiveNegativeUnknownTestsPassed, boolean decisionCacheFullyBound,
            boolean signalSignatureAudienceReplayVerified, boolean authorizationRenewed,
            boolean exceptionUsed, boolean exceptionScopeExact, boolean exceptionActive,
            boolean compensatingControlActive, boolean nonWaivablePolicyOverridden,
            boolean deploymentGateEnvironmentMatches, boolean artifactSignerBuilderValid,
            boolean remediationTypedAndSimulated, boolean remediationReverified,
            boolean logRedactedBeforePersistence, boolean replayInputsAvailable, List<String> evidenceRefs) {
        public DecisionRequest {
            text(organizationId, "organizationId"); text(principal, "principal"); text(action, "action");
            text(resource, "resource"); text(environment, "environment"); digest(contextSnapshotDigest, "contextSnapshotDigest");
            digest(artifactDigest, "artifactDigest"); text(policyId, "policyId"); text(policyVersion, "policyVersion");
            text(bundleRevision, "bundleRevision"); digest(bundleDigest, "bundleDigest"); text(engineVersion, "engineVersion");
            required(language, "language"); required(decisionTime, "decisionTime"); required(decisionExpiresAt, "decisionExpiresAt");
            if (!decisionExpiresAt.isAfter(decisionTime)) throw new IllegalArgumentException("decision expiry must follow decision time");
            required(evaluatedDecision, "evaluatedDecision"); obligations = copy(obligations);
            supportedObligations = copy(supportedObligations); determiningPolicies = copy(determiningPolicies); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record DecisionResult(Readiness readiness, PolicyDecision policyDecision, List<String> blockers,
                                 List<String> obligations, List<String> restrictions,
                                 boolean enforced, boolean externalOperationExecuted, boolean approved) {
        public DecisionResult {
            required(readiness, "readiness"); required(policyDecision, "policyDecision"); blockers = copy(blockers);
            obligations = copy(obligations); restrictions = nonempty(restrictions, "restrictions");
            if (enforced || externalOperationExecuted || approved)
                throw new IllegalArgumentException("PDP result is not an enforcement receipt or approval");
            if (readiness == Readiness.READY_FOR_ENFORCEMENT_GATE && !blockers.isEmpty())
                throw new IllegalArgumentException("enforcement-gate readiness requires no blockers");
        }
    }

    static void text(String value, String field) { if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required"); }
    static void digest(String value, String field) { text(value, field); if (!value.matches("[a-f0-9]{64}")) throw new IllegalArgumentException(field + " must be SHA-256"); }
    static <T> T required(T value, String field) { return Objects.requireNonNull(value, field + " is required"); }
    static <T> List<T> copy(List<T> values) { return values == null ? List.of() : List.copyOf(values); }
    static <T> List<T> nonempty(List<T> values, String field) { if (values == null || values.isEmpty()) throw new IllegalArgumentException(field + " must not be empty"); return List.copyOf(values); }
}
