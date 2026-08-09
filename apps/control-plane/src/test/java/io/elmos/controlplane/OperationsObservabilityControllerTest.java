package io.elmos.controlplane;

import io.elmos.persistence.JdbcUserActivityStore;
import io.elmos.persistence.JdbcUserActivityStore.ActivityEvent;
import io.elmos.persistence.JdbcUserActivityStore.ActivitySummary;
import io.elmos.persistence.JdbcOperationsManagementStore;
import io.elmos.persistence.JdbcRunHistoryStore;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class OperationsObservabilityControllerTest {
    private static final String KEY = "operations-test-key-32-characters";
    private static final Instant NOW = Instant.parse("2026-07-28T10:00:00Z");
    private final JdbcUserActivityStore store = mock(JdbcUserActivityStore.class);
    private final JdbcOperationsManagementStore management = mock(JdbcOperationsManagementStore.class);
    private final JdbcRunHistoryStore runHistory = mock(JdbcRunHistoryStore.class);
    private final OperationsObservabilityController controller =
            controllerWithLeaseExpiring(NOW.plusSeconds(60 * 60).toString());

    /**
     * Authorization moved to {@link OperationsAuthorization}, so the credential
     * lease is configured there rather than on the controller. These tests still
     * drive it through the controller on purpose: what they assert is that an
     * endpoint refuses a bad lease, and that stays true only while the
     * controller keeps delegating.
     */
    private OperationsObservabilityController controllerWithLeaseExpiring(String expiresAt) {
        var authorization = new OperationsAuthorization(
                Clock.fixed(NOW, ZoneOffset.UTC), KEY, expiresAt, "org-1", "actor-1");
        return new OperationsObservabilityController(
                store, management, runHistory,
                Clock.fixed(NOW, ZoneOffset.UTC), authorization, false, false);
    }

    @Test void appendsIdentityBoundBatchWithoutAcceptingIdentityFromThePayload() {
        var event = new ActivityEvent(
                "event-1", "session-1", "USER_ACTION", "CLICK",
                "PROJECT_SYNTHESIS", "/generation", "button:primary-button",
                NOW.minusSeconds(5), 12, "SUCCESS", null, null, null, Map.of());
        when(store.appendTelemetry("org-1", "actor-1", "request-1", List.of(event))).thenReturn(1);

        var result = controller.append(
                KEY, "org-1", "actor-1", "request-1",
                new OperationsObservabilityController.EventBatch(List.of(event)));

        assertEquals(1, result.accepted());
        assertEquals("POSTGRES_RETENTION_MANAGED", result.persistence());
        verify(store).appendTelemetry("org-1", "actor-1", "request-1", List.of(event));
    }

    @Test void summaryUsesBoundedServerTimeWindow() {
        var expected = new ActivitySummary(
                NOW.minusSeconds(24 * 60 * 60), NOW, 12, 3, 1, 8.33, 240,
                List.of(), List.of(), List.of(), "POSTGRES_DUAL_STORE", "NOT_RUN");
        when(store.summary(anyString(), any(), any(), anyString(), anyString(), anyInt()))
                .thenReturn(expected);

        var result = controller.summary(
                KEY, "org-1", "actor-1", "VIEWER", 24, "ALL", "ALL", 50);

        assertEquals(expected, result);
        verify(store).summary(
                "org-1", NOW.minusSeconds(24 * 60 * 60), NOW, "ALL", "ALL", 50);
    }

    @Test void rejectsMissingOrIncorrectInternalCredentialAndOversizedWindows() {
        assertThrows(SecurityException.class,
                () -> controller.summary(
                        "incorrect-key", "org-1", "actor-1", "VIEWER", 24, "ALL", "ALL", 50));
        assertThrows(SecurityException.class,
                () -> controller.summary(
                        KEY, "other-org", "actor-1", "VIEWER", 24, "ALL", "ALL", 50));
        assertThrows(SecurityException.class,
                () -> controller.summary(
                        KEY, "org-1", "invalid actor!", "VIEWER", 24, "ALL", "ALL", 50));
        assertThrows(IllegalArgumentException.class,
                () -> controller.summary(
                        KEY, "org-1", "actor-1", "VIEWER", 745, "ALL", "ALL", 50));
        assertThrows(SecurityException.class,
                () -> controller.evaluate(KEY, "org-1", "actor-1", "VIEWER", "request-1"));
    }

    @Test void rejectsExpiredOrExcessivelyLongInternalCredentialLeases() {
        var expired = controllerWithLeaseExpiring(NOW.minusSeconds(1).toString());
        var excessive = controllerWithLeaseExpiring(NOW.plusSeconds(24 * 60 * 60 + 1).toString());

        assertThrows(RuntimeException.class,
                () -> expired.summary(
                        KEY, "org-1", "actor-1", "VIEWER", 24, "ALL", "ALL", 50));
        assertThrows(RuntimeException.class,
                () -> excessive.summary(
                        KEY, "org-1", "actor-1", "VIEWER", 24, "ALL", "ALL", 50));
    }

    @Test void replayReturnsTheReconstructedRun() {
        var timeline = new JdbcRunHistoryStore.RunTimeline(
                "run-1", "org-1", "snap-1", "plan-1", 1, "COMPLETED",
                new JdbcRunHistoryStore.Section<>(List.of(), false),
                new JdbcRunHistoryStore.Section<>(List.of(), false),
                new JdbcRunHistoryStore.Section<>(List.of(), false));
        when(runHistory.replay("org-1", "run-1")).thenReturn(Optional.of(timeline));

        var result = controller.replay(KEY, "org-1", "actor-1", "VIEWER", "run-1");

        assertEquals("run-1", result.migrationRunId());
        assertEquals("COMPLETED", result.state());
        verify(runHistory).replay("org-1", "run-1");
    }

    /**
     * A missing run and another tenant's run both arrive here as an empty
     * Optional, and both must leave as the same 404. If this ever became a 403
     * for one of them, the status code would confirm that the id exists.
     */
    @Test void replayReportsAnAbsentRunAsNotFound() {
        when(runHistory.replay("org-1", "run-missing")).thenReturn(Optional.empty());

        assertThrows(OperationsObservabilityController.RunHistoryNotFoundException.class,
                () -> controller.replay(KEY, "org-1", "actor-1", "VIEWER", "run-missing"));
    }

    /**
     * The replay must go through the same authorization as the export. Asserting
     * the refusal here is what keeps a future edit from reaching the store
     * before checking the caller -- the store itself has no idea who is asking.
     */
    @Test void replayRefusesAWrongOperationsKey() {
        assertThrows(SecurityException.class,
                () -> controller.replay("wrong-key-wrong-key-wrong-key", "org-1", "actor-1", "VIEWER", "run-1"));
        assertThrows(SecurityException.class,
                () -> controller.replay("x", "org-1", "actor-1", "VIEWER", "run-1"));
        assertThrows(SecurityException.class,
                () -> controller.replay("x".repeat(4_097), "org-1", "actor-1", "VIEWER", "run-1"));
        verify(runHistory, org.mockito.Mockito.never()).replay(anyString(), anyString());
    }
}
