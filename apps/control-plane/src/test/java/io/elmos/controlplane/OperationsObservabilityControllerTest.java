package io.elmos.controlplane;

import io.elmos.persistence.JdbcUserActivityStore;
import io.elmos.persistence.JdbcUserActivityStore.ActivityEvent;
import io.elmos.persistence.JdbcUserActivityStore.ActivitySummary;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;

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
    private final OperationsObservabilityController controller =
            new OperationsObservabilityController(
                    store, Clock.fixed(NOW, ZoneOffset.UTC), KEY,
                    NOW.plusSeconds(60 * 60).toString(), "org-1", "actor-1");

    @Test void appendsIdentityBoundBatchWithoutAcceptingIdentityFromThePayload() {
        var event = new ActivityEvent(
                "event-1", "session-1", "USER_ACTION", "CLICK",
                "PROJECT_SYNTHESIS", "/generation", "button:primary-button",
                NOW.minusSeconds(5), 12, "SUCCESS", null, null, null, Map.of());
        when(store.append("org-1", "actor-1", "request-1", List.of(event))).thenReturn(1);

        var result = controller.append(
                KEY, "org-1", "actor-1", "request-1",
                new OperationsObservabilityController.EventBatch(List.of(event)));

        assertEquals(1, result.accepted());
        assertEquals("POSTGRES_APPEND_ONLY", result.persistence());
        verify(store).append("org-1", "actor-1", "request-1", List.of(event));
    }

    @Test void summaryUsesBoundedServerTimeWindow() {
        var expected = new ActivitySummary(
                NOW.minusSeconds(24 * 60 * 60), NOW, 12, 3, 1, 8.33, 240,
                List.of(), List.of(), List.of(), "POSTGRES_APPEND_ONLY", "NOT_RUN");
        when(store.summary(anyString(), any(), any(), anyString(), anyString(), anyInt()))
                .thenReturn(expected);

        var result = controller.summary(KEY, "org-1", "actor-1", 24, "ALL", "ALL", 50);

        assertEquals(expected, result);
        verify(store).summary(
                "org-1", NOW.minusSeconds(24 * 60 * 60), NOW, "ALL", "ALL", 50);
    }

    @Test void rejectsMissingOrIncorrectInternalCredentialAndOversizedWindows() {
        assertThrows(SecurityException.class,
                () -> controller.summary("incorrect-key", "org-1", "actor-1", 24, "ALL", "ALL", 50));
        assertThrows(SecurityException.class,
                () -> controller.summary(KEY, "other-org", "actor-1", 24, "ALL", "ALL", 50));
        assertThrows(SecurityException.class,
                () -> controller.summary(KEY, "org-1", "other-actor", 24, "ALL", "ALL", 50));
        assertThrows(IllegalArgumentException.class,
                () -> controller.summary(KEY, "org-1", "actor-1", 745, "ALL", "ALL", 50));
    }

    @Test void rejectsExpiredOrExcessivelyLongInternalCredentialLeases() {
        var expired = new OperationsObservabilityController(
                store, Clock.fixed(NOW, ZoneOffset.UTC), KEY,
                NOW.minusSeconds(1).toString(), "org-1", "actor-1");
        var excessive = new OperationsObservabilityController(
                store, Clock.fixed(NOW, ZoneOffset.UTC), KEY,
                NOW.plusSeconds(24 * 60 * 60 + 1).toString(), "org-1", "actor-1");

        assertThrows(RuntimeException.class,
                () -> expired.summary(KEY, "org-1", "actor-1", 24, "ALL", "ALL", 50));
        assertThrows(RuntimeException.class,
                () -> excessive.summary(KEY, "org-1", "actor-1", 24, "ALL", "ALL", 50));
    }
}
