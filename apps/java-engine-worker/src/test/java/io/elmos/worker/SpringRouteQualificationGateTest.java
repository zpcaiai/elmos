package io.elmos.worker;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringRouteQualificationGateTest {
    private static final String COMMIT = "0123456789abcdef0123456789abcdef01234567";
    private static final String DIGEST = "sha256:" + "a".repeat(64);

    @Test void accountsForSixPendingRoutesWithoutPromotingMissingEvidence() {
        var decision = SpringRouteQualificationGate.evaluateMatrix(List.of());
        assertEquals(39, decision.catalogRoutes());
        assertEquals(33, decision.alreadyPassedLocal());
        assertEquals(6, decision.pendingRoutes());
        assertEquals(0, decision.newlyQualifiedLocal());
        assertEquals(6, decision.decisions().size());
        assertTrue(decision.decisions().values().stream()
                .allMatch(item -> item.localStatus() == SpringRouteQualificationGate.LocalStatus.NOT_RUN));
    }

    @Test void separatesLocalExecutionFromCustomerAndIndependentEvidence() {
        var local = SpringRouteQualificationGate.evaluate(evidence(false, false, false));
        assertEquals(SpringRouteQualificationGate.LocalStatus.PASSED_LOCAL, local.localStatus());
        assertEquals(SpringRouteQualificationGate.ExternalStatus.NOT_RUN, local.externalStatus());
        assertTrue(local.blockers().contains("customer repository authorization is absent"));

        var external = SpringRouteQualificationGate.evaluate(evidence(true, true, true));
        assertEquals(SpringRouteQualificationGate.LocalStatus.PASSED_LOCAL, external.localStatus());
        assertEquals(SpringRouteQualificationGate.ExternalStatus.READY_FOR_EXTERNAL_GATE, external.externalStatus());
        assertTrue(external.blockers().isEmpty());
    }

    @Test void failsClosedForBadDigestsMissingRuntimeAndDuplicateEvidence() {
        var invalid = new SpringRouteQualificationGate.RouteExecutionEvidence(
                "boot-1.5-java-8-maven-to-boot-2.7.18-java-17",
                "1.5.22.RELEASE", "8", "short", COMMIT, "bad",
                true, false, true, true, true, true, true, true, true, true);
        var decision = SpringRouteQualificationGate.evaluate(invalid);
        assertEquals(SpringRouteQualificationGate.LocalStatus.NOT_RUN, decision.localStatus());
        assertTrue(decision.blockers().stream().anyMatch(item -> item.contains("source commit")));
        assertTrue(decision.blockers().stream().anyMatch(item -> item.contains("source startup")));

        var item = evidence(false, false, false);
        assertThrows(IllegalArgumentException.class,
                () -> SpringRouteQualificationGate.evaluateMatrix(List.of(item, item)));
    }

    private static SpringRouteQualificationGate.RouteExecutionEvidence evidence(
            boolean authorized, boolean accepted, boolean independentlyVerified) {
        return new SpringRouteQualificationGate.RouteExecutionEvidence(
                "boot-1.5-java-8-maven-to-boot-2.7.18-java-17",
                "1.5.22.RELEASE", "8", COMMIT, COMMIT, DIGEST,
                true, true, true, true, true, true, true,
                authorized, accepted, independentlyVerified);
    }
}
