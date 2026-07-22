package io.elmos.product.policy;

import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.List;
import static io.elmos.product.policy.ContinuousAuthorizationModels.*;
import static org.junit.jupiter.api.Assertions.*;

class ContinuousAuthorizationServiceTest {
    private final ContinuousAuthorizationService service = new ContinuousAuthorizationService();

    @Test void indeterminateMissingContextAndUnknownObligationFailClosed() {
        var result = service.evaluate(request(PolicyDecision.INDETERMINATE, false, List.of("unknown"), List.of()));
        assertEquals(Readiness.BLOCKED, result.readiness()); assertEquals(PolicyDecision.DENY, result.policyDecision());
        assertTrue(result.blockers().contains("CONTEXT_INCOMPLETE"));
        assertTrue(result.blockers().contains("UNSUPPORTED_MANDATORY_OBLIGATION:unknown"));
        assertFalse(result.enforced());
    }

    @Test void validDecisionStillRequiresSeparateEnforcementReceipt() {
        var result = service.evaluate(request(PolicyDecision.ALLOW_WITH_OBLIGATIONS, true, List.of("step-up"), List.of("step-up")));
        assertEquals(Readiness.READY_FOR_ENFORCEMENT_GATE, result.readiness());
        assertEquals(PolicyDecision.ALLOW_WITH_OBLIGATIONS, result.policyDecision());
        assertFalse(result.enforced()); assertFalse(result.approved());
    }

    private static DecisionRequest request(PolicyDecision decision, boolean complete, List<String> obligations, List<String> supported) {
        return new DecisionRequest("org", "principal", "deploy", "service:billing", "production",
                "a".repeat(64), "b".repeat(64), "policy", "v7", "bundle-r9", "c".repeat(64), "opa-1.4",
                PolicyLanguage.REGO_V1, Instant.parse("2026-07-22T00:00:00Z"), Instant.parse("2026-07-22T00:05:00Z"),
                decision, obligations, supported, List.of("policy:v7"), complete, true, true, false, true, false,
                false, true, true, true, true, true, false, false, false, false, false,
                true, true, true, true, true, true, List.of("evidence://decision/42"));
    }
}
