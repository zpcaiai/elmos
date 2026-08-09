package io.elmos.workspaceservice;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import java.util.List;

/**
 * Authenticates the narrow service-to-service surface that can create or mutate
 * isolated workspaces. The three Spring runtime broker endpoints deliberately do
 * not pass through this filter; they retain their body-bound HMAC protocol.
 */
final class WorkspaceServiceCredentialFilter extends OncePerRequestFilter {
    static final String KEY_HEADER = "X-ELMOS-Repository-Key";
    static final String ORGANIZATION_HEADER = "X-ELMOS-Organization-ID";
    static final String ACTOR_HEADER = "X-ELMOS-Actor-ID";
    static final String AUTHORITY = "WORKSPACE_SERVICE";
    static final String PRINCIPAL_ATTRIBUTE =
            "io.elmos.workspaceservice.WorkspaceServiceCredentialFilter.principal";

    private static final int MINIMUM_KEY_BYTES = 24;
    private static final int MAXIMUM_KEY_BYTES = 4096;

    record Principal(String organizationId, String actorId) {}

    private final Clock clock;
    private final int apiKeyBytes;
    private final byte[] apiKeySha256;
    private final String expiresAt;
    private final String boundOrganizationId;
    private final String boundActorId;

    WorkspaceServiceCredentialFilter(
            Clock clock,
            String apiKey,
            String expiresAt,
            String boundOrganizationId,
        String boundActorId
    ) {
        this.clock = clock;
        byte[] normalizedKey = normalized(apiKey).getBytes(StandardCharsets.UTF_8);
        this.apiKeyBytes = normalizedKey.length;
        this.apiKeySha256 = sha256(normalizedKey);
        this.expiresAt = normalized(expiresAt);
        this.boundOrganizationId = normalized(boundOrganizationId);
        this.boundActorId = normalized(boundActorId);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI().substring(request.getContextPath().length());
        return !(path.equals("/api/v1/workspaces")
                || path.startsWith("/api/v1/workspaces/"));
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        if (!configuredFor(clock.instant())) {
            writeError(
                    response,
                    HttpServletResponse.SC_SERVICE_UNAVAILABLE,
                    "WORKSPACE_SERVICE_AUTH_NOT_CONFIGURED",
                    "Workspace service authentication is unavailable.",
                    false);
            return;
        }

        String presentedKey = request.getHeader(KEY_HEADER);
        String presentedOrganization = request.getHeader(ORGANIZATION_HEADER);
        String presentedActor = request.getHeader(ACTOR_HEADER);
        if (presentedKey == null || presentedOrganization == null || presentedActor == null) {
            writeError(
                    response,
                    HttpServletResponse.SC_UNAUTHORIZED,
                    "WORKSPACE_SERVICE_AUTH_REQUIRED",
                    "Workspace service authentication is required.",
                    false);
            return;
        }
        if (!constantTimeKeyEquals(apiKeySha256, presentedKey)
                || !boundOrganizationId.equals(presentedOrganization)
                || !boundActorId.equals(presentedActor)) {
            writeError(
                    response,
                    HttpServletResponse.SC_FORBIDDEN,
                    "WORKSPACE_SERVICE_AUTH_FORBIDDEN",
                    "Workspace service authentication was rejected.",
                    false);
            return;
        }

        Principal principal = new Principal(boundOrganizationId, boundActorId);
        var authentication = new UsernamePasswordAuthenticationToken(
                principal,
                null,
                List.of(new SimpleGrantedAuthority(AUTHORITY)));
        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
        request.setAttribute(PRINCIPAL_ATTRIBUTE, principal);
        filterChain.doFilter(request, response);
    }

    private boolean configuredFor(Instant now) {
        if (apiKeyBytes < MINIMUM_KEY_BYTES
                || apiKeyBytes > MAXIMUM_KEY_BYTES
                || !boundOrganizationId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
                || !boundActorId.matches("[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}")) {
            return false;
        }
        try {
            Instant expiry = Instant.parse(expiresAt);
            return expiry.isAfter(now) && !expiry.isAfter(now.plus(24, ChronoUnit.HOURS));
        } catch (DateTimeParseException error) {
            return false;
        }
    }

    private static boolean constantTimeKeyEquals(byte[] expectedSha256, String presented) {
        byte[] presentedBytes = presented.getBytes(StandardCharsets.UTF_8);
        if (presentedBytes.length > MAXIMUM_KEY_BYTES) {
            return false;
        }
        return MessageDigest.isEqual(
                expectedSha256,
                sha256(presentedBytes));
    }

    private static byte[] sha256(byte[] value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value);
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }

    static void writeError(
            HttpServletResponse response,
            int status,
            String errorCode,
            String message,
            boolean retryable
    ) throws IOException {
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/json");
        response.setHeader("Cache-Control", "no-store");
        response.getWriter().write(
                "{\"errorCode\":\"" + errorCode
                        + "\",\"message\":\"" + message
                        + "\",\"retryable\":" + retryable + "}");
    }

    private static String normalized(String value) {
        return value == null ? "" : value.trim();
    }
}
