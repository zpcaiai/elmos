package io.elmos.delivery;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.delivery.DeliveryModels.*;
import io.elmos.validation.ValidationModels.Status;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class DeliveryGovernanceTest {
    private static final Instant NOW = Instant.parse("2026-07-21T00:00:00Z");
    private static final ObjectMapper JSON = new ObjectMapper();
    private static KeyPair keyPair;

    @BeforeAll
    static void keys() throws Exception {
        keyPair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
    }

    @Test
    void reportsAreDerivedFromOneImmutableEvidenceSnapshot() throws Exception {
        DeliverySnapshot snapshot = readySnapshot();
        ReportBundle report = new ReportGenerator(JSON).generate(snapshot);
        JsonNode authoritative = JSON.readTree(report.authoritativeJson());
        assertEquals(snapshot.migrationId(), authoritative.get("migrationId").asText());
        assertEquals(snapshot.deliveryHeadSha(), authoritative.get("deliveryHeadSha").asText());
        assertTrue(report.markdown().contains(snapshot.deliveryHeadSha()));
        assertTrue(report.html().contains(snapshot.deliveryHeadSha()));
        assertEquals(DeliveryReadModel.hash(report.authoritativeJson()), report.factsHash());
    }

    @Test
    void incompleteEvidenceAndOpenCriticalRiskBlockDelivery() {
        DeliveryReadModel readModel = new DeliveryReadModel(JSON);
        DeliverySnapshot incomplete = readModel.assemble("migration-1", "source-1", "source-sha", "head-sha",
                null, null, List.of(), List.of(), null, null, NOW);
        assertEquals(SnapshotStatus.INCOMPLETE, incomplete.status());
        RiskItem critical = new RiskItem("risk-1", "fingerprint-1", RiskSeverity.CRITICAL, RiskStatus.OPEN,
                "Irreversible data change", "owner@example.com", null, null, List.of("evidence://risk/1"));
        DeliverySnapshot blocked = readModel.assemble("migration-1", "source-1", "source-sha", "head-sha",
                "validation-1", Status.PASS, facts(), List.of(critical), "rollback-1", "pack-1", NOW);
        assertEquals(SnapshotStatus.BLOCKED, blocked.status());
        assertTrue(blocked.blockingReasons().contains("CRITICAL_RISK_OPEN:risk-1"));
    }

    @Test
    void scmPlansAreAlwaysDraftIdempotentAndNeverForcePushOrAutoMerge() {
        ScmDeliveryPolicy policy = new ScmDeliveryPolicy();
        ScmDeliveryPlan first = policy.plan(ScmProvider.GITHUB, "acme/orders", "Migration 123", "main", "head-sha",
                "Modernize orders", "Evidence-bound delivery", List.of("team-platform"));
        ScmDeliveryPlan second = policy.plan(ScmProvider.GITHUB, "acme/orders", "Migration 123", "main", "head-sha",
                "Modernize orders", "Evidence-bound delivery", List.of("team-platform"));
        assertTrue(first.draft()); assertFalse(first.forcePush()); assertFalse(first.autoMerge());
        assertEquals(first.idempotencyKey(), second.idempotencyKey());
        assertEquals("elmos/migration-123", first.branchName());
    }

    @Test
    void githubAnnotationsAreChunkedAtFiftyAndHeadChangeMakesCheckStale() {
        List<Annotation> annotations = new ArrayList<>();
        for (int index = 1; index <= 101; index++) annotations.add(new Annotation("src/A.java", index, index, "failure", "Issue", "Message", "evidence://" + index));
        ScmDeliveryPolicy policy = new ScmDeliveryPolicy();
        CheckPublication published = policy.check(ScmProvider.GITHUB, null, "ELMOS Quality", "head-a", "head-a",
                CheckConclusion.SUCCESS, annotations, "quality passed");
        assertEquals(List.of(50, 50, 1), published.annotationBatches().stream().map(List::size).toList());
        CheckPublication stale = policy.check(ScmProvider.GITHUB, null, "ELMOS Quality", "head-a", "head-b",
                CheckConclusion.SUCCESS, annotations, "old result");
        assertTrue(stale.stale()); assertEquals(CheckConclusion.STALE, stale.conclusion());
    }

    @Test
    void gitlabUltimateUsesExternalStatusAndLowerTiersUseCommitStatusFallback() {
        ScmDeliveryPolicy policy = new ScmDeliveryPolicy();
        assertEquals(CheckTransport.GITLAB_EXTERNAL_STATUS, policy.check(ScmProvider.GITLAB, GitLabTier.ULTIMATE,
                "ELMOS", "a", "a", CheckConclusion.SUCCESS, List.of(), "ok").transport());
        assertEquals(CheckTransport.GITLAB_COMMIT_STATUS, policy.check(ScmProvider.GITLAB, GitLabTier.PREMIUM,
                "ELMOS", "a", "a", CheckConclusion.SUCCESS, List.of(), "ok").transport());
        assertEquals(CheckTransport.GITLAB_COMMIT_STATUS, policy.check(ScmProvider.GITLAB, GitLabTier.FREE,
                "ELMOS", "a", "a", CheckConclusion.SUCCESS, List.of(), "ok").transport());
    }

    @Test
    void signedEvidencePackIsDeterministicAndTamperingFailsVerification() {
        EvidencePackService service = new EvidencePackService(JSON);
        List<EvidenceEntry> entries = List.of(
                new EvidenceEntry("evidence/validation.json", "{\"status\":\"PASS\"}".getBytes(), "application/json", false),
                new EvidenceEntry("reports/summary.md", "# Passed".getBytes(), "text/markdown", false));
        EvidencePack first = service.create(entries, keyPair.getPrivate(), keyPair.getPublic());
        EvidencePack second = service.create(entries, keyPair.getPrivate(), keyPair.getPublic());
        assertArrayEquals(first.archive(), second.archive());
        assertTrue(service.verify(first, keyPair.getPublic()));
        byte[] altered = first.archive(); altered[altered.length / 2] ^= 1;
        EvidencePack tampered = new EvidencePack(first.packId(), altered, first.manifest(), first.signature(), first.publicKey(),
                first.archiveSha256(), first.entries());
        assertFalse(service.verify(tampered, keyPair.getPublic()));
        assertThrows(SecurityException.class, () -> service.create(List.of(
                new EvidenceEntry("evidence/full-source/repo.tar", new byte[]{1}, "application/x-tar", false)), keyPair.getPrivate(), keyPair.getPublic()));
    }

    @Test
    void irreversibleDatabaseChangeUsesRestoreAndRollForwardNotCodeRevertAlone() {
        RollbackPlan plan = new RollbackPlanner().plan("migration-1",
                List.of(new Change("database", "drop legacy column", false, true, false, "artifact://schema-diff")),
                30, 5, DrillStatus.PASSED);
        assertTrue(plan.executable());
        assertTrue(plan.steps().stream().anyMatch(step -> step.action() == RollbackActionType.RESTORE_DATABASE));
        assertTrue(plan.steps().stream().anyMatch(step -> step.action() == RollbackActionType.ROLL_FORWARD));
        assertFalse(plan.steps().stream().anyMatch(step -> step.action() == RollbackActionType.REVERT_CODE));
    }

    @Test
    void incompatibleCacheRequiresDualReadAndRtoRpoAreNeverInvented() {
        RollbackPlanner planner = new RollbackPlanner();
        RollbackPlan cache = planner.plan("migration-1", List.of(new Change("cache", "cache v2", true, false, false, "artifact://cache")),
                15, 0, DrillStatus.NOT_RUN);
        assertTrue(cache.steps().stream().anyMatch(step -> step.action() == RollbackActionType.DUAL_READ_CACHE));
        RollbackPlan missing = planner.plan("migration-1", List.of(new Change("code", "upgrade", true, false, true, "artifact://patch")),
                null, null, DrillStatus.NOT_RUN);
        assertFalse(missing.executable());
        assertTrue(missing.blockingReasons().containsAll(List.of("RTO_NOT_SUPPLIED", "RPO_NOT_SUPPLIED")));
    }

    @Test
    void conditionalAcceptanceIsSeparateFromMergeReleaseAndClosureAndIsHeadBound() {
        AcceptancePolicy policy = new AcceptancePolicy();
        List<AcceptanceCriterion> criteria = List.of(new AcceptanceCriterion("quality", "Quality gate", true, true, "evidence://quality"));
        AcceptancePackage conditional = policy.evaluate("migration-1", "head-a", "head-a", criteria,
                List.of("monitor for seven days"), false, false, false, "owner@example.com", NOW);
        assertEquals(AcceptanceStatus.CONDITIONALLY_ACCEPTED, conditional.acceptanceStatus());
        assertEquals(DeliveryLifecycle.ACCEPTED, conditional.lifecycle());
        AcceptancePackage conditionalClosure = policy.evaluate("migration-1", "head-a", "head-a", criteria,
                List.of("monitor for seven days"), true, true, true, "owner@example.com", NOW);
        assertEquals(AcceptanceStatus.CONDITIONALLY_ACCEPTED, conditionalClosure.acceptanceStatus());
        assertEquals(DeliveryLifecycle.RELEASED, conditionalClosure.lifecycle());
        assertTrue(conditionalClosure.blockingReasons().contains("CONDITIONAL_ACCEPTANCE_OPEN"));
        AcceptancePackage noHuman = policy.evaluate("migration-1", "head-a", "head-a", criteria,
                List.of("monitor for seven days"), false, false, false, null, null);
        assertEquals(AcceptanceStatus.READY_FOR_ACCEPTANCE, noHuman.acceptanceStatus());
        AcceptancePackage closed = policy.evaluate("migration-1", "head-a", "head-a", criteria,
                List.of(), true, true, true, "owner@example.com", NOW);
        assertEquals(DeliveryLifecycle.CLOSED, closed.lifecycle());
        AcceptancePackage stale = policy.evaluate("migration-1", "head-a", "squash-head", criteria,
                List.of(), true, true, true, "owner@example.com", NOW);
        assertEquals(AcceptanceStatus.NOT_READY, stale.acceptanceStatus());
        assertTrue(stale.blockingReasons().contains("ACCEPTANCE_HEAD_STALE"));
    }

    @Test
    void deliveryFactsAndRiskAcceptanceMustRemainEvidenceBound() {
        DeliverySnapshot snapshot = new DeliveryReadModel(JSON).assemble("migration-1", "snapshot-1",
                "source", "head", "validation-1", Status.PASS,
                List.of(new EvidenceFact("fact", "quality", "PASS", "claim", List.of(), Map.of())),
                List.of(), "rollback", "pack", NOW);
        assertEquals(SnapshotStatus.INCOMPLETE, snapshot.status());
        assertTrue(snapshot.blockingReasons().contains("DELIVERY_EVIDENCE_REFERENCE_MISSING"));
        assertThrows(IllegalArgumentException.class, () -> new RiskItem("risk", "fingerprint",
                RiskSeverity.CRITICAL, RiskStatus.ACCEPTED, "accepted risk", "owner", null,
                null, List.of("evidence://risk")));
    }

    private static DeliverySnapshot readySnapshot() {
        return new DeliveryReadModel(JSON).assemble("migration-1", "source-1", "source-sha", "head-sha",
                "validation-1", Status.PASS, facts(), List.of(), "rollback-1", "pack-1", NOW);
    }
    private static List<EvidenceFact> facts() {
        return List.of(new EvidenceFact("fact-1", "quality", "PASS", "Independent validation passed",
                List.of("evidence://validation/1"), Map.of("tests", 42)));
    }
}
