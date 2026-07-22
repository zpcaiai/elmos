package io.elmos.product.policy;

import java.util.ArrayList;
import java.util.List;

import static io.elmos.product.policy.ContinuousAuthorizationModels.*;

/** Deterministic PDP admission. It deliberately performs no PEP side effect. */
public final class ContinuousAuthorizationService {
    public DecisionResult evaluate(DecisionRequest request) {
        required(request, "request"); List<String> blockers = new ArrayList<>();
        require(request.contextComplete(), "CONTEXT_INCOMPLETE", blockers);
        require(request.contextFresh(), "CONTEXT_STALE", blockers);
        require(request.factsTrusted(), "UNTRUSTED_POLICY_FACT", blockers);
        if (request.factsConflicted()) blockers.add("FACT_CONFLICT_UNRESOLVED");
        require(request.bundleSigned(), "UNSIGNED_POLICY_BUNDLE", blockers);
        if (request.bundleRevoked()) blockers.add("POLICY_BUNDLE_REVOKED");
        if (request.bundleExpired()) blockers.add("POLICY_BUNDLE_EXPIRED");
        require(request.languageTypeChecked(), "POLICY_LANGUAGE_VALIDATION_REQUIRED", blockers);
        require(request.positiveNegativeUnknownTestsPassed(), "POLICY_TEST_MATRIX_INCOMPLETE", blockers);
        require(request.decisionCacheFullyBound(), "DECISION_CACHE_BINDING_INCOMPLETE", blockers);
        require(request.signalSignatureAudienceReplayVerified(), "SECURITY_SIGNAL_VALIDATION_REQUIRED", blockers);
        require(request.authorizationRenewed(), "AUTHORIZATION_RENEWAL_REQUIRED", blockers);
        if (request.exceptionUsed()) {
            require(request.exceptionScopeExact(), "EXCEPTION_SCOPE_NOT_EXACT", blockers);
            require(request.exceptionActive(), "EXCEPTION_INACTIVE_OR_EXPIRED", blockers);
            require(request.compensatingControlActive(), "COMPENSATING_CONTROL_REQUIRED", blockers);
        }
        if (request.nonWaivablePolicyOverridden()) blockers.add("NON_WAIVABLE_POLICY_OVERRIDE_FORBIDDEN");
        require(request.deploymentGateEnvironmentMatches(), "DEPLOYMENT_GATE_ENVIRONMENT_MISMATCH", blockers);
        require(request.artifactSignerBuilderValid(), "ARTIFACT_SIGNER_BUILDER_INVALID", blockers);
        require(request.remediationTypedAndSimulated(), "REMEDIATION_PLAN_AND_SIMULATION_REQUIRED", blockers);
        require(request.remediationReverified(), "REMEDIATION_REVERIFICATION_REQUIRED", blockers);
        require(request.logRedactedBeforePersistence(), "DECISION_LOG_REDACTION_REQUIRED", blockers);
        require(request.replayInputsAvailable(), "DECISION_REPLAY_INPUTS_REQUIRED", blockers);
        if (request.determiningPolicies().isEmpty()) blockers.add("DETERMINING_POLICY_REQUIRED");
        for (String obligation : request.obligations())
            if (!request.supportedObligations().contains(obligation)) blockers.add("UNSUPPORTED_MANDATORY_OBLIGATION:" + obligation);
        if (request.evidenceRefs().isEmpty()) blockers.add("IMMUTABLE_DECISION_EVIDENCE_REQUIRED");
        if (request.evaluatedDecision() == PolicyDecision.INDETERMINATE || request.evaluatedDecision() == PolicyDecision.NOT_APPLICABLE)
            blockers.add("NON_ALLOW_DECISION:" + request.evaluatedDecision());
        List<String> result = blockers.stream().distinct().sorted().toList();
        PolicyDecision safeDecision = result.isEmpty() ? request.evaluatedDecision() : PolicyDecision.DENY;
        return new DecisionResult(result.isEmpty() ? Readiness.READY_FOR_ENFORCEMENT_GATE : Readiness.BLOCKED,
                safeDecision, result, request.obligations(), List.of(
                "PAP_PIP_PDP_AND_PEP_REMAIN_SEPARATE", "A_DECISION_IS_NOT_AN_ENFORCEMENT_RECEIPT",
                "INDETERMINATE_NOT_APPLICABLE_AND_ERRORS_NEVER_MEAN_ALLOW", "ACTIVE_POLICY_VERSIONS_ARE_IMMUTABLE",
                "DEPLOYMENT_AND_RUNTIME_SIDE_EFFECTS_REQUIRE_A_FRESH_PEP_RECEIPT"), false, false, false);
    }
    private static void require(boolean value, String blocker, List<String> blockers) { if (!value) blockers.add(blocker); }
}
