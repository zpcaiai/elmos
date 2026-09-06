package io.elmos.liveworkbench;

import io.elmos.developerworkflow.DeveloperWorkflowService;
import io.elmos.developerworkflow.IdeProtocolGateway;
import io.elmos.developerworkflow.LocalPreviewEngine;
import io.elmos.developerworkflow.OwnershipPolicyEngine;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.liveworkbench.LwContracts.*;
import static org.junit.jupiter.api.Assertions.*;

class LiveWorkbenchServiceTest {
    private static final String SNAPSHOT = LwDigest.sha256("snapshot");
    private static final String ARTIFACT = LwDigest.sha256("artifact");

    @Test void immutableSourceUsesUtf8BytesAndRejectsCrossTenantReads() {
        ImmutableSourceRepository sources = new ImmutableSourceRepository();
        String text = "// emoji \uD83D\uDE80\nreturn 1;\n";
        int end = text.getBytes(StandardCharsets.UTF_8).length;
        SourceAnchor anchor = sources.store("tenant-a", "repo", SNAPSHOT, "src/Main.java", "Main", text, 0, end);
        Authority valid = authority("session", 1, "tenant-a", Set.of(Capability.INSPECT));
        assertEquals(text, sources.resolve(valid, anchor, 100));
        Authority foreign = authority("session", 1, "tenant-b", Set.of(Capability.INSPECT));
        assertThrows(SecurityException.class, () -> sources.resolve(foreign, anchor, 100));
        assertThrows(IllegalArgumentException.class, () -> new SourceAnchor("tenant-a", "repo", SNAPSHOT, "../secret", ARTIFACT, 0, 1, "utf8-byte-half-open", "x"));
    }

    @Test void readinessCreatesOneFixed600SecondWindowAndCleanupReleasesSlots() {
        PreviewSessionManager manager = new PreviewSessionManager((session, reason, now) -> new CleanupReceipt(session.binding(), session.expiresAt(), now,
                Map.of("proxy_revoked", true, "connections_closed", true, "processes_stopped", true, "secrets_revoked", true), SessionState.CLEANED, "fake-host", List.of("cleanup-1")));
        Authority authority = authority("s1", 1, "tenant-a", Set.of(Capability.HOST_EXEC, Capability.INSPECT, Capability.CONTROL));
        PreviewSession preparing = manager.create(authority, 10, 1_000, 1);
        assertEquals(SessionState.PREPARING, preparing.state());
        ReadinessAttestation attestation = new ReadinessAttestation("ready-1", authority.binding(), ARTIFACT, "independent-verifier", "host-signature-ref", 100,
                Map.of("authenticated", true, "business_smoke", true, "capacity", true), List.of("smoke-1"), true);
        PreviewSession ready = manager.commitReady(authority, attestation, 100);
        assertEquals(700, ready.expiresAt()); assertFalse(ready.clientCanExtend()); assertTrue(ready.liveAt(699)); assertFalse(ready.liveAt(700));
        assertThrows(IllegalStateException.class, () -> manager.commitReady(authority, attestation, 100));
        assertThrows(IllegalStateException.class, () -> manager.expireOrTerminate(authority, "s1", "refresh", 101));
        assertEquals(SessionState.CLEANED, manager.expireOrTerminate(authority, "s1", "deadline", 701).status());
        // A released slot permits another session; no hidden renewal is possible.
        assertEquals(SessionState.PREPARING, manager.create(authority("s2", 1, "tenant-a", Set.of(Capability.HOST_EXEC)), 702, 2_000, 3).state());
    }

    @Test void debugLedgerFencesGenerationAndNeverRetriesUnknownEffects() {
        PreviewSession session = readySession();
        Authority authority = authority("s1", 1, "tenant-a", Set.of(Capability.CONTROL, Capability.INSPECT));
        DebugCommandLedger ledger = new DebugCommandLedger();
        DebugCommand command = new DebugCommand(authority.binding(), "cmd-1", "idem-1", 0, "controller", "next", LwDigest.sha256("{}"), Capability.CONTROL, "host-authority", 700);
        assertEquals(CommandState.UNKNOWN, ledger.submit(authority, session, command, 200, false).state());
        assertEquals("RECONCILE_BEFORE_RETRY", ledger.submit(authority, session, command, 200, true).code());
        DebugCommand changed = new DebugCommand(authority.binding(), "cmd-2", "idem-1", 0, "controller", "continue", LwDigest.sha256("{}"), Capability.CONTROL, "host-authority", 700);
        assertEquals("IDEMPOTENCY_PAYLOAD_CONFLICT", ledger.submit(authority, session, changed, 200, true).code());
        RuntimeEvent event = new RuntimeEvent("event-1", authority.binding(), 0, 1, "stopped", 201, List.of("anchor-1"), LwDigest.sha256("payload"), true, "redacted");
        ledger.appendCommitted(event);
        assertEquals(1, ledger.resume(authority, 0, 202).size());
        assertThrows(IllegalArgumentException.class, () -> ledger.appendCommitted(event));
    }

    @Test void workbenchNavigationClaimsAndMissionsFailClosedOnStaleness() {
        LiveWorkbenchService service = service();
        SourceAnchor source = new SourceAnchor("tenant-a", "repo", SNAPSHOT, "src/A.java", ARTIFACT, 0, 1, "utf8-byte-half-open", "A");
        SourceAnchor target = new SourceAnchor("tenant-a", "repo", SNAPSHOT, "src/A.cs", ARTIFACT, 0, 1, "utf8-byte-half-open", "A");
        service.registerNavigation(new LiveWorkbenchService.NavigationNode("source", source, "source"));
        service.registerNavigation(new LiveWorkbenchService.NavigationNode("target", target, "target"));
        service.registerNavigationEdge(new LiveWorkbenchService.NavigationEdge("source", "target", "one-to-one", 1.0, List.of("map-evidence")));
        Authority authority = authority("s1", 1, "tenant-a", Set.of(Capability.INSPECT));
        assertEquals("RESOLVED", service.navigate(authority, "source", SNAPSHOT, .99, 10).status());
        assertEquals("STALE", service.navigate(authority, "source", LwDigest.sha256("new"), .99, 10).status());
        assertThrows(IllegalArgumentException.class, () -> new EvidenceClaim("bad", "tenant-a", "repo", SNAPSHOT, "it ran", ClaimClass.RUNTIME_OBSERVED, List.of("a"), List.of(), List.of(), List.of(), "v1"));
        LearningMission mission = new LearningMission("m1", "tenant-a", "repo", SNAPSHOT, "Read A", "Guided", "beginner", List.of(), List.of("a"),
                List.of(new MissionStep("step", "Read it", "read", "server-grader", List.of())), "private-grader", false);
        service.registerMission(mission); assertTrue(service.missionForSnapshot("m1", LwDigest.sha256("other")).stale()); assertFalse(mission.answerInPublicPayload());
        assertEquals(28, LiveWorkbenchService.supportedSkills().size());
        assertEquals(SkillStatus.BLOCKED_BY_HOST, LiveWorkbenchService.supportedSkills().get("elmos-lw-native-device-lab"));
    }

    private static LiveWorkbenchService service() {
        PreviewSessionManager manager = new PreviewSessionManager((session, reason, now) -> new CleanupReceipt(session.binding(), session.expiresAt() == null ? now : session.expiresAt(), now,
                Map.of("all", true), SessionState.CLEANED, "host", List.of("e")));
        DeveloperWorkflowService workflow = new DeveloperWorkflowService(new IdeProtocolGateway("1.0.0", Set.of("migration-cli"), Map.of()), new OwnershipPolicyEngine(List.of()), new LocalPreviewEngine());
        return new LiveWorkbenchService(new ImmutableSourceRepository(), manager, new DebugCommandLedger(), workflow);
    }
    private static PreviewSession readySession() {
        Binding binding = new Binding("tenant-a", "repo", SNAPSHOT, "s1", 1);
        return new PreviewSession(binding, SessionState.READY, RuntimeStatus.RUNNING, 0, 100L, 700L, PREVIEW_SECONDS, CLEANUP_SECONDS, 800, 1, "ready", false);
    }
    private static Authority authority(String session, int generation, String tenant, Set<Capability> capabilities) {
        return new Authority("host", "account-a", "env", "lease", 2_000, new Binding(tenant, "repo", SNAPSHOT, session, generation), capabilities);
    }
}
