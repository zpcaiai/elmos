package io.elmos.scm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class WebhookIngestionService {
    public enum Result { ACCEPTED, DUPLICATE }
    public record Delivery(String deliveryId, String eventType, String action, Long repositoryExternalId,
                           Long installationExternalId, String payloadSha256, Instant receivedAt, String normalizedEventType) {}
    public interface DeliveryStore { boolean recordAndEnqueueIfAbsent(Delivery delivery); }

    private final GithubWebhookVerifier verifier;
    private final DeliveryStore store;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final int maxBodyBytes;

    public WebhookIngestionService(GithubWebhookVerifier verifier, DeliveryStore store,
                                   ObjectMapper objectMapper, Clock clock, int maxBodyBytes) {
        this.verifier = Objects.requireNonNull(verifier); this.store = Objects.requireNonNull(store);
        this.objectMapper = Objects.requireNonNull(objectMapper);
        this.clock = Objects.requireNonNull(clock);
        if (maxBodyBytes < 1024) throw new IllegalArgumentException("maxBodyBytes must be at least 1024");
        this.maxBodyBytes = maxBodyBytes;
    }

    public Result ingest(String deliveryId, String eventType, String signature, byte[] rawBody, List<char[]> secrets) {
        requireHeader(deliveryId, "delivery id", 128); requireHeader(eventType, "event type", 64);
        if (rawBody == null || rawBody.length > maxBodyBytes) throw new IllegalArgumentException("webhook body exceeds limit");
        if (!verifier.verify(rawBody, signature, secrets)) throw new SecurityException("invalid webhook signature");
        try {
            JsonNode payload = objectMapper.readTree(rawBody);
            String action = text(payload, "action");
            Delivery delivery = new Delivery(deliveryId, eventType, action,
                    number(payload.path("repository"), "id"), number(payload.path("installation"), "id"),
                    HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(rawBody)), clock.instant(), normalize(eventType, action));
            if (!store.recordAndEnqueueIfAbsent(delivery)) return Result.DUPLICATE;
            return Result.ACCEPTED;
        } catch (SecurityException exception) { throw exception; }
        catch (Exception exception) { throw new IllegalArgumentException("invalid webhook payload", exception); }
    }

    private static void requireHeader(String value, String name, int maxLength) {
        if (value == null || value.isBlank() || value.length() > maxLength) throw new IllegalArgumentException("invalid " + name);
    }
    private static String text(JsonNode node, String field) { JsonNode value = node.get(field); return value == null || value.isNull() ? null : value.asText(); }
    private static Long number(JsonNode node, String field) { JsonNode value = node.get(field); return value == null || !value.canConvertToLong() ? null : value.longValue(); }
    private static String normalize(String event, String action) {
        return switch (event) {
            case "installation" -> switch (String.valueOf(action)) {
                case "created" -> "GithubInstallationCreated"; case "deleted" -> "GithubInstallationRemoved";
                case "suspended" -> "GithubInstallationSuspended"; case "unsuspended", "new_permissions_accepted" -> "GithubInstallationChanged";
                default -> null;
            };
            case "installation_repositories" -> switch (String.valueOf(action)) {
                case "added" -> "GithubRepositoryAuthorized"; case "removed" -> "GithubRepositoryAuthorizationRemoved"; default -> null;
            };
            case "repository" -> action != null && Set.of("archived", "unarchived", "deleted", "renamed", "transferred", "visibility_changed").contains(action)
                    ? "GithubRepositoryChanged" : null;
            case "push" -> "GithubPushObserved";
            case "pull_request" -> action != null && Set.of("opened", "synchronize", "reopened", "closed").contains(action) ? "GithubPullRequestChanged" : null;
            case "check_run" -> action != null && Set.of("rerequested", "requested_action").contains(action) ? "GithubCheckRerequested" : null;
            default -> null;
        };
    }
}
