package io.elmos.proofloop;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static io.elmos.proofloop.ProofLoopModels.CertificateLevel;
import static io.elmos.proofloop.ProofLoopModels.EvidenceAssertion;
import static io.elmos.proofloop.ProofLoopModels.EvidenceState;
import static io.elmos.proofloop.ProofLoopModels.ExecutionRequest;
import static io.elmos.proofloop.ProofLoopModels.RunState;
import static io.elmos.proofloop.ProofLoopModels.Subject;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ModernizationProofLoopEngineTest {
    private static final Instant NOW = Instant.parse("2026-08-05T12:00:00Z");
    private static final String ZEROS = "sha256:" + "0".repeat(64);
    private static final String ONES = "sha256:" + "1".repeat(64);
    private static final String COMMIT_A = "a".repeat(40);
    private static final String COMMIT_B = "b".repeat(40);
    private final SkillContractCatalog catalog = new SkillContractCatalog();
    private final ProofLoopOperators operators = new ProofLoopOperators(Duration.ofHours(24));

    @Test
    void loadsAllImmutableContractsAndClosurePlan() {
        assertEquals(64, catalog.all().size());
        assertEquals(64, catalog.plan("B108-S16").size());
        assertEquals("B105-S01", catalog.plan("B108-S16").getFirst().id());
        assertEquals("B108-S16", catalog.plan("B108-S16").getLast().id());
    }

    @Test
    void callerSuccessAndCertificationFieldsCannotForgeAResult() {
        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("PASS", true);
        inputs.put("certified", true);
        inputs.put("productionReady", true);
        inputs.put("licenseAllowed", true);
        inputs.put("hasBuild", true);
        inputs.put("hasTests", true);
        inputs.put("hasVisibleService", true);
        var outcome = operators.evaluate(catalog.require("B105-S01"), request("B105-S01", inputs, Map.of()), NOW);
        assertEquals(RunState.BLOCKED, outcome.state());
        assertTrue(outcome.findings().contains("verified_evidence_missing:dependency:B104-S16"));
        assertEquals(CertificateLevel.NONE, outcome.certificateLevel());
        assertFalse(outcome.payload().containsKey("productionApproved"));
    }

    @Test
    void ttlStartsOnlyAtReadyAndCannotExceedTenMinutes() {
        Map<String, Object> valid = Map.of(
                "createdAt", "2026-08-05T11:58:00Z",
                "readyAt", "2026-08-05T12:00:00Z",
                "expiresAt", "2026-08-05T12:10:00Z",
                "ttlSeconds", 600);
        var passed = operators.evaluate(catalog.require("B106-S13"),
                request("B106-S13", valid, verified("execution:B106-S13")), NOW);
        assertEquals(RunState.PASSED, passed.state());

        Map<String, Object> invalid = Map.of(
                "createdAt", "2026-08-05T11:58:00Z",
                "readyAt", "2026-08-05T12:00:00Z",
                "expiresAt", "2026-08-05T12:10:00Z",
                "ttlSeconds", 660);
        var blocked = operators.evaluate(catalog.require("B106-S13"),
                request("B106-S13", invalid, verified("execution:B106-S13")), NOW);
        assertEquals(RunState.BLOCKED, blocked.state());
        assertTrue(blocked.findings().contains("ttl_not_anchored_to_ready_timestamp"));
        assertTrue(blocked.findings().contains("ttl_outside_1_600_seconds"));
    }

    @Test
    void cleanupRequiresRouteRevocationBeforeProviderDestroy() {
        Map<String, ProofLoopModels.EvidenceAssertion> evidence = verified(
                "execution:B106-S15", "cleanup:route-revocation", "cleanup:provider-destroy",
                "cleanup:secret-revocation", "cleanup:orphan-recheck", "cleanup:cost-finalization");
        Map<String, Object> inputs = Map.of(
                "routeRevokedAt", "2026-08-05T12:00:05Z",
                "instanceDestroyedAt", "2026-08-05T12:00:00Z",
                "temporaryVolumesDeleted", true,
                "orphanCount", 0);
        var outcome = operators.evaluate(catalog.require("B106-S15"), request("B106-S15", inputs, evidence), NOW);
        assertEquals(RunState.BLOCKED, outcome.state());
        assertTrue(outcome.findings().contains("cleanup_order_must_revoke_route_before_destroy"));
    }

    @Test
    void certificateCannotJumpOrAuthorizeProduction() {
        Map<String, Object> inputs = Map.of("requestedCertificateLevel", "PRODUCTION_CANDIDATE");
        Map<String, EvidenceAssertion> evidence = verified(
                "gate:B108-S16", "certificate:PRODUCTION_CANDIDATE", "certificate:CLEANUP_ATTESTED");
        var outcome = operators.evaluate(catalog.require("B108-S16"), request("B108-S16", inputs, evidence), NOW);
        assertEquals(RunState.BLOCKED, outcome.state());
        assertTrue(outcome.findings().contains("certificate_prerequisite_missing:CODE_MODIFIED"));
        assertEquals(false, outcome.payload().get("productionApproved"));
        assertEquals(false, outcome.payload().get("deployAuthorized"));
    }

    @Test
    void engineRejectsEvidenceBoundToAnotherSubjectAndPropagatesBlock() {
        ModernizationProofLoopEngine engine = engine();
        Map<String, Object> inputs = Map.of(
                "licenseAllowed", true, "hasBuild", true, "hasTests", true, "hasVisibleService", true);
        ExecutionRequest request = request("B105-S01", inputs, Map.of(
                "dependency:B104-S16", assertion(ONES)));
        var result = engine.execute("B105-S01", request);
        assertEquals(RunState.BLOCKED, result.state());
        assertTrue(result.steps().getFirst().findings().stream()
                .anyMatch(finding -> finding.startsWith("evidence_subject_mismatch:")));
        assertFalse(result.productionApproved());
        assertFalse(result.certified());
    }

    @Test
    void planReceiptsAreDeterministicAtAFixedClock() {
        ModernizationProofLoopEngine engine = engine();
        ExecutionRequest request = request("B105-S01", Map.of(), Map.of());
        var first = engine.execute("B105-S01", request);
        var second = engine.execute("B105-S01", request);
        assertEquals(first.planId(), second.planId());
        assertEquals(first.steps().getFirst().resultDigest(), second.steps().getFirst().resultDigest());
        assertTrue(first.steps().getFirst().artifacts().getFirst().sha256().startsWith("sha256:"));
    }

    @Test
    void modelRejectsCallerClaimsOfExternalExecution() {
        assertThrows(IllegalArgumentException.class, () -> new ProofLoopModels.SkillResult(
                "run-1", "request-1", "B105-S01", "selector", 105, RunState.BLOCKED,
                List.of(), List.of("blocked"), List.of(), ZEROS, ONES, NOW, NOW,
                true, false, CertificateLevel.NONE));
    }

    private ModernizationProofLoopEngine engine() {
        return new ModernizationProofLoopEngine(catalog, operators, new ObjectMapper(),
                Clock.fixed(NOW, ZoneOffset.UTC));
    }

    private ExecutionRequest request(
            String skillId,
            Map<String, Object> inputs,
            Map<String, EvidenceAssertion> evidence
    ) {
        return new ExecutionRequest("run-1", "request-1", skillId, "actor-1", subject(), NOW, inputs, evidence);
    }

    private Subject subject() {
        return new Subject("org-1", "project-1", "repository-1", COMMIT_A, COMMIT_B, ONES, ZEROS);
    }

    private Map<String, EvidenceAssertion> verified(String... keys) {
        Map<String, EvidenceAssertion> result = new LinkedHashMap<>();
        for (String key : keys) result.put(key, assertion(ZEROS));
        return Map.copyOf(result);
    }

    private EvidenceAssertion assertion(String subjectDigest) {
        return new EvidenceAssertion(EvidenceState.VERIFIED, subjectDigest, "runner-1", "verifier-1", NOW,
                true, true, List.of("artifact:sha256:" + "2".repeat(64)));
    }
}
