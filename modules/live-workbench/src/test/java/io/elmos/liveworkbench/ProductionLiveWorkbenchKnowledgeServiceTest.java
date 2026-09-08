package io.elmos.liveworkbench;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.liveworkbench.LwContracts.*;
import static io.elmos.liveworkbench.ProductionContracts.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ProductionLiveWorkbenchKnowledgeServiceTest {
    @Test void assessmentUsesCommittedRuntimeEventsAndNeverAcceptsClientPassedFlag() {
        LiveWorkbenchCatalogStore catalog = mock(LiveWorkbenchCatalogStore.class);
        LiveWorkbenchStore sessions = mock(LiveWorkbenchStore.class);
        SandboxProviderPort provider = mock(SandboxProviderPort.class);
        String snapshot = LwDigest.sha256("snapshot");
        LearningMission mission = new LearningMission("mission-a", "tenant-a", "repo-a", snapshot, "Inspect value",
                "Guided", "engineer", List.of(), List.of("anchor-a"),
                List.of(new MissionStep("step-a", "Inspect it", "inspect", "private-predicate", List.of())),
                "private-grader", false);
        PrincipalScope scope = new PrincipalScope("tenant-a", "account-a", "actor-a", "env-a",
                Set.of("workbench.learning.attempt"));
        SessionView ready = new SessionView("tenant-a", "account-a", "actor-a", "session-a", "delivery-a", "repo-a",
                snapshot, "node", "learn", "learn", 1, 1, SessionState.READY, RuntimeStatus.RUNNING,
                1, 10L, 610L, 700, "provider-a", "lease-a", Map.of("sandbox", "sandbox-a"), List.of("evidence"), 1);
        MissionAttemptRequest request = new MissionAttemptRequest("session-a", 1, LwDigest.sha256("private answer"), List.of("event-a"));
        MissionAttemptReceipt pending = new MissionAttemptReceipt("attempt-a", "assessment-key", CommandState.PENDING,
                null, List.of(), List.of(), 0);
        MissionAttemptReceipt committed = new MissionAttemptReceipt("attempt-a", "assessment-key", CommandState.COMMITTED,
                92, List.of("feedback-a"), List.of("assessment-evidence"), 1);
        when(catalog.mission("tenant-a", "mission-a")).thenReturn(java.util.Optional.of(mission));
        when(sessions.find("tenant-a", "session-a")).thenReturn(java.util.Optional.of(ready));
        when(sessions.events("tenant-a", "session-a", 0, 500)).thenReturn(List.of(
                new EventView("event-a", "session-a", 1, 1, 1, "stopped", LwDigest.sha256("event"),
                        List.of("anchor-a"), "redacted", 12)));
        when(catalog.reserveAttempt(eq("tenant-a"), eq("actor-a"), eq("mission-a"), eq(request), anyString(),
                eq("assessment-key"), anyString(), eq(100L)))
                .thenReturn(new LiveWorkbenchCatalogStore.AttemptReservation(pending, true));
        when(provider.assess(scope, mission, request, "attempt-a", "assessment-key")).thenReturn(committed);
        when(catalog.completeAttempt("tenant-a", "actor-a", "mission-a", "assessment-key", committed, 100)).thenReturn(committed);

        MissionAttemptReceipt result = new ProductionLiveWorkbenchKnowledgeService(catalog, sessions, provider,
                Clock.fixed(Instant.ofEpochSecond(100), ZoneOffset.UTC)).attempt(scope, "mission-a", request, "assessment-key");

        assertEquals(92, result.score());
        assertFalse(mission.answerInPublicPayload());
        verify(provider).assess(scope, mission, request, "attempt-a", "assessment-key");
        verify(catalog).completeAttempt("tenant-a", "actor-a", "mission-a", "assessment-key", committed, 100);
    }

    @Test void uncommittedAssessmentEventFailsBeforeProviderCall() {
        LiveWorkbenchCatalogStore catalog = mock(LiveWorkbenchCatalogStore.class);
        LiveWorkbenchStore sessions = mock(LiveWorkbenchStore.class);
        SandboxProviderPort provider = mock(SandboxProviderPort.class);
        String snapshot = LwDigest.sha256("snapshot");
        LearningMission mission = new LearningMission("mission-a", "tenant-a", "repo-a", snapshot, "Inspect value",
                "Guided", "engineer", List.of(), List.of("anchor-a"),
                List.of(new MissionStep("step-a", "Inspect it", "inspect", "private-predicate", List.of())), "grader", false);
        PrincipalScope scope = new PrincipalScope("tenant-a", "account-a", "actor-a", "env-a",
                Set.of("workbench.learning.read", "workbench.learning.attempt"));
        when(catalog.mission("tenant-a", "mission-a")).thenReturn(java.util.Optional.of(mission));
        when(sessions.find("tenant-a", "session-a")).thenReturn(java.util.Optional.of(new SessionView(
                "tenant-a", "account-a", "actor-a", "session-a", "delivery-a", "repo-a", snapshot, "node", "learn",
                "learn", 1, 1, SessionState.READY, RuntimeStatus.RUNNING, 1, 10L, 610L, 700, "provider", "lease",
                Map.of("sandbox", "sandbox"), List.of("evidence"), 1)));
        when(sessions.events("tenant-a", "session-a", 0, 500)).thenReturn(List.of());
        MissionAttemptRequest request = new MissionAttemptRequest("session-a", 1, LwDigest.sha256("answer"), List.of("missing"));

        assertThrows(LiveWorkbenchException.class, () -> new ProductionLiveWorkbenchKnowledgeService(catalog, sessions,
                provider, Clock.fixed(Instant.ofEpochSecond(100), ZoneOffset.UTC)).attempt(scope, "mission-a", request, "assessment-key"));
        verifyNoInteractions(provider);
    }
}
