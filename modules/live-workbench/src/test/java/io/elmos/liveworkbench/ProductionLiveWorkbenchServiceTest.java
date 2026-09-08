package io.elmos.liveworkbench;

import io.elmos.product.execution.SecureExecutionAdmissionService;
import io.elmos.product.execution.SecureExecutionModels;
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

class ProductionLiveWorkbenchServiceTest {
    private static final long NOW = 1_000;
    private static final String SNAPSHOT = LwDigest.sha256("snapshot");

    @Test void createsOnlyAfterStrictAdmissionAndReturnsBoundPreparingSession() {
        LiveWorkbenchStore store = mock(LiveWorkbenchStore.class);
        SandboxProviderPort provider = mock(SandboxProviderPort.class);
        PrincipalScope scope = scope("workbench.session.create");
        CreateSessionRequest request = request();
        SessionView reserved = session(null, 0, SessionState.PREPARING);
        SessionView bound = session("provider-1", NOW + 930, SessionState.PREPARING);
        when(store.reserve(eq(scope), eq(request), anyString(), eq("request-key-001"), anyString(), eq(NOW)))
                .thenReturn(new LiveWorkbenchStore.Reservation(reserved, true));
        when(provider.preflight(eq(scope), eq(reserved.sessionId()), eq(request), eq("admission-request-key-001")))
                .thenReturn(admission(true));
        ProviderAllocation allocation = new ProviderAllocation("provider-1", "lease-1", NOW + 930,
                Map.of("sandbox", "sb-1"), List.of("provider-evidence"));
        when(provider.allocate(eq(scope), eq(reserved.sessionId()), eq(request), eq("request-key-001"), eq(NOW + 930)))
                .thenReturn(allocation);
        when(store.bindProvider(scope.tenantId(), reserved.sessionId(), 0, allocation)).thenReturn(bound);

        ApiSession result = service(store, provider).create(scope, request, "request-key-001");

        assertEquals("provider-1", result.session().providerSessionId());
        assertEquals(SessionState.PREPARING, result.session().state());
        verify(store).recordAudit(eq(scope.tenantId()), eq(scope.actorId()), eq(reserved.sessionId()),
                eq("SANDBOX_ALLOCATED"), eq("PREPARING"), anyString(), eq(NOW));
    }

    @Test void replayedSessionRequestNeverAllocatesTwice() {
        LiveWorkbenchStore store = mock(LiveWorkbenchStore.class);
        SandboxProviderPort provider = mock(SandboxProviderPort.class);
        SessionView bound = session("provider-1", NOW + 930, SessionState.PREPARING);
        when(store.reserve(any(), any(), anyString(), anyString(), anyString(), anyLong()))
                .thenReturn(new LiveWorkbenchStore.Reservation(bound, false));

        ApiSession result = service(store, provider).create(scope("workbench.session.create"), request(), "request-key-002");

        assertEquals("provider-1", result.session().providerSessionId());
        verifyNoInteractions(provider);
    }

    @Test void failedSandboxAdmissionIsDurableAndNeverAllocates() {
        LiveWorkbenchStore store = mock(LiveWorkbenchStore.class);
        SandboxProviderPort provider = mock(SandboxProviderPort.class);
        PrincipalScope scope = scope("workbench.session.create");
        SessionView reserved = session(null, 0, SessionState.PREPARING);
        when(store.reserve(any(), any(), anyString(), anyString(), anyString(), anyLong()))
                .thenReturn(new LiveWorkbenchStore.Reservation(reserved, true));
        when(provider.preflight(any(), anyString(), any(), anyString())).thenReturn(admission(false));
        when(store.find(scope.tenantId(), reserved.sessionId())).thenReturn(java.util.Optional.of(
                session(null, 0, SessionState.FAILED)));
        when(store.failPreparation(eq(scope.tenantId()), eq(reserved.sessionId()), eq(0L), anyString(), eq(NOW)))
                .thenReturn(session(null, 0, SessionState.FAILED));

        LiveWorkbenchException error = assertThrows(LiveWorkbenchException.class,
                () -> service(store, provider).create(scope, request(), "request-key-003"));

        assertEquals("ROOTLESS_EXECUTION_REQUIRED", error.code());
        verify(provider, never()).allocate(any(), anyString(), any(), anyString(), anyLong());
        verify(store).failPreparation(scope.tenantId(), reserved.sessionId(), 0, "ROOTLESS_EXECUTION_REQUIRED", NOW);
    }

    @Test void unknownDebugReplayReconcilesWithoutRedispatch() {
        LiveWorkbenchStore store = mock(LiveWorkbenchStore.class);
        SandboxProviderPort provider = mock(SandboxProviderPort.class);
        PrincipalScope scope = scope("workbench.debug.control");
        SessionView ready = session("provider-1", NOW + 930, SessionState.READY);
        DebugRequest request = new DebugRequest("next", LwDigest.sha256("{}"), 4, "control-lease");
        DebugReceipt unknown = new DebugReceipt("command-1", "debug-key-001", CommandState.UNKNOWN,
                "RECONCILIATION_REQUIRED", null, 1);
        DebugReceipt committed = new DebugReceipt("command-1", "debug-key-001", CommandState.COMMITTED,
                "PROVIDER_COMMITTED", "evidence-1", 2);
        when(store.find(scope.tenantId(), ready.sessionId())).thenReturn(java.util.Optional.of(ready));
        when(store.reserveCommand(eq(scope.tenantId()), eq(ready.sessionId()), eq(1), eq(request), anyString(),
                eq("debug-key-001"), anyString(), eq(NOW)))
                .thenReturn(new LiveWorkbenchStore.CommandReservation(unknown, false));
        when(provider.reconcileDebug(scope, ready, "command-1", "debug-key-001"))
                .thenReturn(new ProviderCommandResult(CommandState.COMMITTED, "evidence-1", LwDigest.sha256("result")));
        when(store.completeCommand(eq(scope.tenantId()), eq(ready.sessionId()), eq("debug-key-001"), any(), eq(NOW)))
                .thenReturn(committed);

        DebugReceipt result = service(store, provider).debug(scope, ready.sessionId(), 1, request, "debug-key-001");

        assertEquals(CommandState.COMMITTED, result.state());
        verify(provider, never()).dispatchDebug(any(), any(), anyString(), anyString(), any());
    }

    @Test void readinessTimestampCannotMintAWindowInTheFuture() {
        LiveWorkbenchStore store = mock(LiveWorkbenchStore.class);
        SandboxProviderPort provider = mock(SandboxProviderPort.class);
        PrincipalScope scope = scope("workbench.runtime.commit");
        when(store.find(scope.tenantId(), "session-a")).thenReturn(java.util.Optional.of(
                session("provider-1", NOW + 2_000, SessionState.PREPARING)));
        ReadinessRequest future = new ReadinessRequest(LwDigest.sha256("artifact"), "verifier", "signature", NOW + 61,
                Map.of("smoke", true), List.of("evidence"));

        LiveWorkbenchException error = assertThrows(LiveWorkbenchException.class,
                () -> service(store, provider).markReady(scope, "session-a", 0, future));

        assertEquals("READINESS_TIMESTAMP_INVALID", error.code());
        verify(store, never()).commitReady(anyString(), anyString(), anyLong(), any());
    }

    @Test void expiredSessionRejectsRuntimeEventsBeforePersistence() {
        LiveWorkbenchStore store = mock(LiveWorkbenchStore.class);
        SandboxProviderPort provider = mock(SandboxProviderPort.class);
        PrincipalScope scope = scope("workbench.runtime.event");
        SessionView expired = new SessionView("tenant-a", "account-a", "actor-a", "session-a", "delivery-a", "repo-a",
                SNAPSHOT, "node-ts-linux", "smoke", "debug", 1, 1, SessionState.READY, RuntimeStatus.RUNNING,
                NOW - 700, NOW - 601, NOW - 1, NOW + 30, "provider-1", "lease-1", Map.of("sandbox", "sb-1"),
                List.of(), 1);
        when(store.find(scope.tenantId(), expired.sessionId())).thenReturn(java.util.Optional.of(expired));
        RuntimeEventRequest event = new RuntimeEventRequest("event-a", 1, 0, 1, "stdout", LwDigest.sha256("event"),
                List.of(), "redacted", NOW);

        LiveWorkbenchException error = assertThrows(LiveWorkbenchException.class,
                () -> service(store, provider).appendRuntimeEvent(scope, expired.sessionId(), event));

        assertEquals("EVENT_SESSION_EXPIRED_OR_NOT_READY", error.code());
        verify(store, never()).appendEvent(anyString(), anyString(), any());
    }

    private static ProductionLiveWorkbenchService service(LiveWorkbenchStore store, SandboxProviderPort provider) {
        LiveWorkbenchCatalogStore catalog = mock(LiveWorkbenchCatalogStore.class);
        when(catalog.delivery(anyString(), anyString())).thenReturn(java.util.Optional.of(delivery()));
        when(catalog.profile(anyString(), anyString())).thenReturn(java.util.Optional.of(profile()));
        return new ProductionLiveWorkbenchService(store, catalog, provider, new SecureExecutionAdmissionService(),
                Clock.fixed(Instant.ofEpochSecond(NOW), ZoneOffset.UTC));
    }

    private static LiveWorkbenchService.ArtifactDelivery delivery() {
        LiveWorkbenchService.CapabilityStatus available = new LiveWorkbenchService.CapabilityStatus(
                SkillStatus.AVAILABLE, "qualified", List.of("evidence"));
        return new LiveWorkbenchService.ArtifactDelivery("delivery-a", "tenant-a", "repo-a", SNAPSHOT, "generated", null,
                LwDigest.sha256("artifact"), LwDigest.sha256("lock"), "node-ts-linux", "main", "web",
                Map.of("read", available, "teach", available, "build", available, "preview", available,
                        "debug", available, "compare", available), List.of(), List.of("postgres-demo"));
    }

    private static RuntimeProfile profile() {
        return new RuntimeProfile("node-ts-linux", "typescript", "next", "node-24", "linux", "amd64", "dap", "1",
                LwDigest.sha256("runtime"), "web", Qualification.QUALIFIED, Set.of("debug"),
                List.of("evidence"), List.of(), false);
    }

    private static PrincipalScope scope(String authority) {
        return new PrincipalScope("tenant-a", "account-a", "actor-a", "environment-a", Set.of(authority));
    }

    private static CreateSessionRequest request() {
        return new CreateSessionRequest("delivery-a", "repo-a", SNAPSHOT, "node-ts-linux", "smoke", "debug", 1, true);
    }

    private static SessionView session(String providerSession, long providerDeadline, SessionState state) {
        Long ready = state == SessionState.READY ? NOW - 10 : null;
        Long expires = state == SessionState.READY ? NOW + 590 : null;
        return new SessionView("tenant-a", "account-a", "actor-a", "session-a", "delivery-a", "repo-a", SNAPSHOT,
                "node-ts-linux", "smoke", "debug", 1, 1, state,
                state == SessionState.READY ? RuntimeStatus.RUNNING : RuntimeStatus.PENDING,
                NOW - 20, ready, expires, providerDeadline, providerSession,
                providerSession == null ? null : "lease-1", providerSession == null ? Map.of() : Map.of("sandbox", "sb-1"),
                List.of(), 0);
    }

    private static SecureExecutionModels.AdmissionRequest admission(boolean rootless) {
        String raw = SNAPSHOT.substring("sha256:".length());
        return new SecureExecutionModels.AdmissionRequest("tenant-a", "session-a", "runner-a", 1, raw, raw,
                SecureExecutionModels.IsolationProvider.ROOTLESS_OCI, Instant.ofEpochSecond(NOW),
                true, true, true, true, true, true, true, true,
                true, rootless, true, true, true, false, true, true, true, true,
                true, true, true, false, true, true, true, true, List.of("admission-evidence"));
    }
}
