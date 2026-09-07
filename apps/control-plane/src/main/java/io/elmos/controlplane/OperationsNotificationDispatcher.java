package io.elmos.controlplane;

import io.elmos.persistence.JdbcOperationsManagementStore;
import io.elmos.persistence.JdbcOperationsManagementStore.PendingNotification;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Set;
import java.util.UUID;

/**
 * Optional, fail-closed HTTPS alert delivery worker.
 *
 * <p>Rows are leased transactionally by the persistence store. The configured
 * destination is exact, secrets are read from a local secret file, payloads
 * carry an idempotency key and HMAC, and failures are reduced to stable codes.
 * No token, payload or remote response body is logged.</p>
 */
@Component
final class OperationsNotificationDispatcher {
    private static final Logger LOG =
            LoggerFactory.getLogger(OperationsNotificationDispatcher.class);
    private static final Set<PosixFilePermission> UNSAFE_PERMISSIONS = Set.of(
            PosixFilePermission.GROUP_READ,
            PosixFilePermission.GROUP_WRITE,
            PosixFilePermission.GROUP_EXECUTE,
            PosixFilePermission.OTHERS_READ,
            PosixFilePermission.OTHERS_WRITE,
            PosixFilePermission.OTHERS_EXECUTE);

    private final JdbcOperationsManagementStore management;
    private final Clock clock;
    private final HttpClient client;
    private final boolean enabled;
    private final String organizationId;
    private final String actorId;
    private final URI webhook;
    private final byte[] hmacSecret;

    @Autowired
    OperationsNotificationDispatcher(
            JdbcOperationsManagementStore management,
            Clock clock,
            @Value("${elmos.operations.notification-enabled:false}") boolean enabled,
            @Value("${elmos.operations.notification-webhook-url:}") String webhookUrl,
            @Value("${elmos.operations.notification-hmac-secret-file:}") String secretFile,
            @Value("${elmos.operations.organization-id:}") String organizationId,
            @Value("${elmos.operations.actor-id:}") String actorId
    ) {
        this(
                management,
                clock,
                HttpClient.newBuilder()
                        .connectTimeout(Duration.ofSeconds(5))
                        .followRedirects(HttpClient.Redirect.NEVER)
                        .build(),
                enabled,
                organizationId,
                actorId,
                parseWebhook(webhookUrl),
                readSecret(secretFile));
    }

    OperationsNotificationDispatcher(
            JdbcOperationsManagementStore management,
            Clock clock,
            HttpClient client,
            boolean enabled,
            String organizationId,
            String actorId,
            URI webhook,
            byte[] hmacSecret
    ) {
        this.management = management;
        this.clock = clock;
        this.client = client;
        this.enabled = enabled;
        this.organizationId = organizationId == null ? "" : organizationId.trim();
        this.actorId = actorId == null ? "" : actorId.trim();
        this.webhook = webhook;
        this.hmacSecret = hmacSecret.clone();
    }

    @Scheduled(fixedDelayString = "${elmos.operations.notification-interval-ms:15000}")
    void deliver() {
        if (!ready()) return;
        Instant now = clock.instant();
        final java.util.List<PendingNotification> notifications;
        try {
            notifications = management.claimPendingNotifications(organizationId, now, 20);
        } catch (RuntimeException error) {
            LOG.warn("Operations notification claim failed with code NOTIFICATION_STORE_UNAVAILABLE");
            return;
        }
        for (PendingNotification notification : notifications) {
            deliver(notification);
        }
    }

    private void deliver(PendingNotification notification) {
        boolean delivered = false;
        String errorCode = "NOTIFICATION_DELIVERY_FAILED";
        try {
            byte[] payload = notification.payload().getBytes(StandardCharsets.UTF_8);
            HttpRequest request = HttpRequest.newBuilder(webhook)
                    .timeout(Duration.ofSeconds(10))
                    .header("Content-Type", "application/json")
                    .header("X-ELMOS-Notification-ID", notification.notificationId())
                    .header("X-ELMOS-Alert-ID", notification.alertId())
                    .header("X-ELMOS-Signature", "sha256=" + signature(hmacSecret, payload))
                    .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
                    .build();
            HttpResponse<Void> response = client.send(
                    request, HttpResponse.BodyHandlers.discarding());
            delivered = response.statusCode() >= 200 && response.statusCode() < 300;
            errorCode = delivered
                    ? "NONE"
                    : "WEBHOOK_HTTP_" + Math.min(599, Math.max(400, response.statusCode()));
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            errorCode = "WEBHOOK_INTERRUPTED";
        } catch (Exception error) {
            errorCode = "WEBHOOK_TRANSPORT_ERROR";
        }
        try {
            management.completeNotificationDelivery(
                    organizationId,
                    actorId,
                    "notification-" + UUID.randomUUID(),
                    notification,
                    delivered,
                    errorCode,
                    clock.instant());
        } catch (RuntimeException error) {
            LOG.warn("Operations notification completion failed with code NOTIFICATION_LEASE_CONFLICT");
        }
    }

    private boolean ready() {
        return enabled
                && !organizationId.isBlank()
                && !actorId.isBlank()
                && webhook != null
                && hmacSecret.length >= 32;
    }

    static URI parseWebhook(String configured) {
        if (configured == null || configured.isBlank()) return null;
        try {
            URI uri = URI.create(configured.trim());
            if (!"https".equalsIgnoreCase(uri.getScheme())
                    || uri.getHost() == null
                    || uri.getUserInfo() != null
                    || uri.getQuery() != null
                    || uri.getFragment() != null) {
                return null;
            }
            return uri;
        } catch (IllegalArgumentException error) {
            return null;
        }
    }

    static byte[] readSecret(String configuredPath) {
        if (configuredPath == null || configuredPath.isBlank()) return new byte[0];
        try {
            Path path = Path.of(configuredPath.trim());
            if (!path.isAbsolute() || !Files.isRegularFile(path)) return new byte[0];
            try {
                Set<PosixFilePermission> permissions = Files.getPosixFilePermissions(path);
                if (permissions.stream().anyMatch(UNSAFE_PERMISSIONS::contains)) {
                    return new byte[0];
                }
            } catch (UnsupportedOperationException ignored) {
                // Non-POSIX stores rely on the platform secret mount ACL.
            }
            byte[] value = Files.readAllBytes(path);
            if (value.length < 32 || value.length > 4096) return new byte[0];
            return value;
        } catch (Exception error) {
            return new byte[0];
        }
    }

    static String signature(byte[] secret, byte[] payload) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(payload));
        } catch (Exception error) {
            throw new IllegalStateException("HMAC_SHA256_UNAVAILABLE", error);
        }
    }
}
