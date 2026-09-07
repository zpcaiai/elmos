package io.elmos.controlplane;

import io.elmos.persistence.JdbcOperationsManagementStore;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

class OperationsAutomationSchedulerTest {
    private static final Instant NOW = Instant.parse("2026-07-28T10:00:00Z");

    @Test
    void runsDetectionAndRetentionOnlyWhenExplicitlyEnabledAndBound() {
        JdbcOperationsManagementStore store = mock(JdbcOperationsManagementStore.class);
        var enabled = new OperationsAutomationScheduler(
                store, Clock.fixed(NOW, ZoneOffset.UTC),
                true, true, 30, "org-1", "operations-bot");

        enabled.evaluate();
        enabled.enforceRetention();

        verify(store).evaluate(eq("org-1"), eq("operations-bot"), any(), eq(NOW));
        verify(store).enforceRetention(
                eq("org-1"), eq("operations-bot"), any(), eq(30), eq(NOW));
    }

    @Test
    void disabledAutomationHasNoSideEffects() {
        JdbcOperationsManagementStore store = mock(JdbcOperationsManagementStore.class);
        var disabled = new OperationsAutomationScheduler(
                store, Clock.fixed(NOW, ZoneOffset.UTC),
                false, false, 30, "org-1", "operations-bot");

        disabled.evaluate();
        disabled.enforceRetention();

        verify(store, never()).evaluate(any(), any(), any(), any());
        verify(store, never()).enforceRetention(any(), any(), any(), any(Integer.class), any());
    }
}
