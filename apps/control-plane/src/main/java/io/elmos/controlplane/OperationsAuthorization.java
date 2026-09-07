package io.elmos.controlplane;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import java.util.Locale;
import java.util.Objects;

/**
 * The single decision point for operations-console authorization.
 *
 * <p>Extracted from {@code OperationsObservabilityController}, where it was a
 * pair of private methods, once a second controller needed the same decision.
 * Copying it would have been faster and is the reason authorization drifts:
 * two copies agree on the day they are written and diverge on the first day
 * somebody tightens one of them. A tightened rule that only half the endpoints
 * enforce is worse than the untightened rule, because the gap is now invisible.
 *
 * <p>Two modes, deliberately not merged:
 * <ul>
 *   <li>{@link #requireView} -- the caller is acting <em>as</em> a specific
 *       actor, so the credential path pins the actor to the configured
 *       identity. Used where the request writes something attributable.</li>
 *   <li>{@link #requireManagement} -- the caller is reading or steering the
 *       console on behalf of a role, so the actor only has to be well-formed
 *       and the role has to outrank the requirement.</li>
 * </ul>
 *
 * <p>Behaviour is preserved exactly as it was in the controller, including one
 * asymmetry worth naming rather than quietly fixing: the OIDC branch ranks
 * {@code adminRole} as returned, while the credential branch normalizes case
 * and whitespace first. Changing that here would mean an extraction silently
 * altered who gets in, which is the one thing an extraction must not do. It is
 * recorded so it can be decided on its own terms.
 */
@Component
final class OperationsAuthorization {

    private final Clock clock;
    private final String apiKey;
    private final byte[] apiKeyDigest;
    private final String apiKeyExpiresAt;
    private final String boundOrganizationId;
    private final String boundActorId;

    OperationsAuthorization(
            Clock clock,
            @Value("${elmos.operations.api-key:}") String apiKey,
            @Value("${elmos.operations.api-key-expires-at:}") String apiKeyExpiresAt,
            @Value("${elmos.operations.organization-id:}") String boundOrganizationId,
            @Value("${elmos.operations.actor-id:}") String boundActorId
    ) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.apiKey = apiKey == null ? "" : apiKey.trim();
        this.apiKeyDigest = sha256(this.apiKey.getBytes(StandardCharsets.UTF_8));
        this.apiKeyExpiresAt = apiKeyExpiresAt == null ? "" : apiKeyExpiresAt.trim();
        this.boundOrganizationId = boundOrganizationId == null ? "" : boundOrganizationId.trim();
        this.boundActorId = boundActorId == null ? "" : boundActorId.trim();
    }

    /**
     * Authorizes a call made as a named actor. The credential path requires the
     * actor to be exactly the configured one, because the resulting rows are
     * attributed to them.
     */
    void requireView(String presentedKey, String organizationId, String actorId) {
        var principal = ControlPlanePrincipal.current();
        if (principal.isPresent()) {
            try {
                principal.get().require(organizationId, actorId, "workspace:view");
                return;
            } catch (RuntimeException error) {
                throw new SecurityException("OIDC audit authorization failed", error);
            }
        }
        requireCredential(presentedKey, organizationId);
        if (!boundActorId.equals(actorId)) {
            throw new SecurityException("operations observability identity binding failed");
        }
    }

    /**
     * Authorizes a console read or workflow transition at a minimum role.
     *
     * @param requiredRole one of {@code VIEWER}, {@code OPERATOR},
     *                     {@code APPROVER}, in increasing order of authority
     */
    void requireManagement(
            String presentedKey,
            String organizationId,
            String actorId,
            String role,
            String requiredRole
    ) {
        var principal = ControlPlanePrincipal.current();
        if (principal.isPresent()) {
            try {
                principal.get().require(organizationId, actorId, "admin:read");
            } catch (RuntimeException error) {
                throw new SecurityException("OIDC operations authorization failed", error);
            }
            if (roleRank(principal.get().adminRole(organizationId)) < roleRank(requiredRole)) {
                throw new SecurityException("OIDC operations role is insufficient");
            }
            return;
        }
        requireCredential(presentedKey, organizationId);
        if (actorId == null
                || !actorId.matches("[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}")) {
            throw new SecurityException("operations administrator identity is invalid");
        }
        requireRole(role, requiredRole);
    }

    /**
     * A credential that is missing, too short, unbound, expired, or valid for
     * longer than a day is treated as "not configured" rather than "denied":
     * none of those states is something the caller can fix by presenting a
     * different key.
     */
    private void requireCredential(String presentedKey, String organizationId) {
        Instant expiry;
        try {
            expiry = Instant.parse(apiKeyExpiresAt);
        } catch (DateTimeParseException error) {
            throw new ObservabilityUnavailableException();
        }
        Instant now = clock.instant();
        if (apiKey.length() < 24
                || boundOrganizationId.isBlank()
                || boundActorId.isBlank()
                || !expiry.isAfter(now)
                || expiry.isAfter(now.plus(24, ChronoUnit.HOURS))) {
            throw new ObservabilityUnavailableException();
        }
        if (!boundOrganizationId.equals(organizationId)) {
            throw new SecurityException("operations observability identity binding failed");
        }
        // Hash both sides to the same fixed width before the constant-time
        // comparison. This avoids exposing the configured key length through
        // an early length mismatch while the bound prevents an oversized
        // header from becoming an avoidable CPU or allocation sink.
        String candidate = presentedKey == null ? "" : presentedKey;
        if (candidate.length() > 4_096) {
            throw new SecurityException("operations observability authorization failed");
        }
        byte[] presentedDigest = sha256(candidate.getBytes(StandardCharsets.UTF_8));
        if (!MessageDigest.isEqual(apiKeyDigest, presentedDigest)) {
            throw new SecurityException("operations observability authorization failed");
        }
    }

    private static byte[] sha256(byte[] value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value);
        } catch (java.security.NoSuchAlgorithmException unavailable) {
            throw new IllegalStateException("SHA-256 is unavailable", unavailable);
        }
    }

    private static void requireRole(String role, String requiredRole) {
        if (roleRank(normalizeRole(role)) < roleRank(requiredRole)) {
            throw new SecurityException("operations role is insufficient");
        }
    }

    /** An unrecognized role ranks below {@code VIEWER}, so an unknown role is refused rather than admitted. */
    private static int roleRank(String role) {
        return switch (role) {
            case "VIEWER" -> 1;
            case "OPERATOR" -> 2;
            case "APPROVER" -> 3;
            default -> 0;
        };
    }

    private static String normalizeRole(String role) {
        return role == null ? "" : role.trim().toUpperCase(Locale.ROOT);
    }
}
