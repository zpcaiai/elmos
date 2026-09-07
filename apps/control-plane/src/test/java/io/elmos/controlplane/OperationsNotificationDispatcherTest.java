package io.elmos.controlplane;

import io.elmos.persistence.JdbcOperationsManagementStore;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Clock;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

class OperationsNotificationDispatcherTest {
    @Test
    void acceptsOnlyExactHttpsWebhookDestinations() {
        assertThat(OperationsNotificationDispatcher.parseWebhook(
                "https://alerts.example.test/elmos")).isEqualTo(
                URI.create("https://alerts.example.test/elmos"));
        assertThat(OperationsNotificationDispatcher.parseWebhook(
                "http://alerts.example.test/elmos")).isNull();
        assertThat(OperationsNotificationDispatcher.parseWebhook(
                "https://user:secret@alerts.example.test/elmos")).isNull();
        assertThat(OperationsNotificationDispatcher.parseWebhook(
                "https://alerts.example.test/elmos?token=secret")).isNull();
    }

    @Test
    void hmacIsDeterministicAndPayloadBound() {
        byte[] secret = "01234567890123456789012345678901"
                .getBytes(StandardCharsets.UTF_8);
        String first = OperationsNotificationDispatcher.signature(
                secret, "{}".getBytes(StandardCharsets.UTF_8));
        String second = OperationsNotificationDispatcher.signature(
                secret, "{\"a\":1}".getBytes(StandardCharsets.UTF_8));

        assertThat(first).hasSize(64).isNotEqualTo(second);
    }

    @Test
    void disabledWorkerNeverClaimsOutboxRows() {
        JdbcOperationsManagementStore management =
                mock(JdbcOperationsManagementStore.class);
        var dispatcher = new OperationsNotificationDispatcher(
                management,
                Clock.systemUTC(),
                HttpClient.newHttpClient(),
                false,
                "org-1",
                "operations-bot",
                URI.create("https://alerts.example.test/elmos"),
                "01234567890123456789012345678901"
                        .getBytes(StandardCharsets.UTF_8));

        dispatcher.deliver();

        verifyNoInteractions(management);
    }
}
