package io.elmos.controlplane;

import io.elmos.identity.AuthenticationService;
import io.elmos.identity.Destinations;
import io.elmos.identity.IdentityStore;
import io.elmos.identity.Secrets;
import io.elmos.identity.SessionCookies;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import jakarta.servlet.http.HttpServletRequest;

/**
 * HTTP surface for authentication.
 *
 * <p>Verification status: compiled against signature-faithful Spring stubs (see
 * {@code springcheck/}). The service beneath it is verified end to end against a
 * real PostgreSQL by {@code AuthenticationServiceTest}.</p>
 *
 * <p>This class is deliberately thin. Every security decision - what to reveal,
 * when to lock, when to revoke - lives in {@link AuthenticationService}, because
 * a policy spread across controller annotations cannot be reviewed as a whole.
 * What does live here is the browser contract: cookie flags, CSRF, and the rule
 * that the refresh token never appears in a response body.</p>
 */
@RestController
@RequestMapping("/api/v1/auth")
@ConditionalOnProperty(
        prefix = "elmos.identity.local",
        name = "enabled",
        havingValue = "true")
public class AuthenticationController {

    private final AuthenticationService authentication;

    public AuthenticationController(AuthenticationService authentication) {
        this.authentication = authentication;
    }

    // ---- request a code ----------------------------------------------------

    public record ChallengeRequest(String destination, String channel, String purpose) {
    }

    /**
     * Always answers 202 for a well-formed destination, whether or not it is
     * registered. Returning 404 for an unknown number would make this endpoint a
     * registration checker for the entire Chinese mobile range.
     */
    @PostMapping("/challenges")
    public ResponseEntity<?> requestChallenge(@RequestBody ChallengeRequest request,
                                              HttpServletRequest servletRequest) {
        Destinations.Channel channel = parseChannel(request.channel());
        AuthenticationService.Purpose purpose = parsePurpose(request.purpose());
        if (channel == null || purpose == null) {
            return error(HttpStatus.BAD_REQUEST, "ELMOS_AUTH_REQUEST_INVALID");
        }

        AuthenticationService.ChallengeOutcome outcome = authentication.requestChallenge(
                request.destination(), channel, purpose, servletRequest.getRemoteAddr());

        return switch (outcome.status()) {
            case ISSUED -> ResponseEntity.status(HttpStatus.ACCEPTED).body(Map.of(
                    "status", "ISSUED",
                    "destination", outcome.maskedDestination(),
                    "expiresInSeconds", outcome.retryAfterSeconds()));
            case RATE_LIMITED -> ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).body(Map.of(
                    "status", "ERROR",
                    "code", "ELMOS_AUTH_TOO_FREQUENT",
                    "retryAfterSeconds", outcome.retryAfterSeconds()));
            case INVALID_DESTINATION -> error(HttpStatus.BAD_REQUEST, "ELMOS_AUTH_DESTINATION_INVALID");
        };
    }

    // ---- verify and open a session ----------------------------------------

    public record VerifyRequest(String destination, String channel, String purpose, String code) {
    }

    /**
     * Sign-up and sign-in are the same call. The client cannot ask for one or the
     * other, because asking would itself reveal whether the destination exists.
     *
     * <p>The refresh token goes into an HttpOnly cookie and never into the body,
     * so a cross-site script cannot read it even if one runs.</p>
     */
    @PostMapping("/sessions")
    public ResponseEntity<?> verify(@RequestBody VerifyRequest request,
                                    HttpServletRequest servletRequest,
                                    @RequestHeader(value = "User-Agent", required = false) String userAgent) {
        Destinations.Channel channel = parseChannel(request.channel());
        AuthenticationService.Purpose purpose = parsePurpose(request.purpose());
        if (channel == null || purpose == null || request.code() == null) {
            return error(HttpStatus.BAD_REQUEST, "ELMOS_AUTH_REQUEST_INVALID");
        }

        AuthenticationService.VerifyOutcome outcome = authentication.verifyAndOpenSession(
                request.destination(), channel, purpose, request.code(),
                servletRequest.getRemoteAddr(), null,
                SessionCookies.clientFamily(userAgent));

        return switch (outcome.status()) {
            case SIGNED_IN, SIGNED_UP -> issueSession(outcome.session(), outcome.status().name());
            // One response for a wrong code and an unknown destination alike.
            case INVALID, INVALID_DESTINATION -> error(HttpStatus.UNAUTHORIZED, "ELMOS_AUTH_INVALID_CODE");
            case LOCKED -> error(HttpStatus.FORBIDDEN, "ELMOS_AUTH_ACCOUNT_LOCKED");
        };
    }

    // ---- refresh -----------------------------------------------------------

    /**
     * REUSE_DETECTED and REJECTED both send the client back to sign-in, but they
     * are different answers on the wire so the front end can tell the user their
     * session was ended for safety rather than silently expired - and so the
     * metric is separable from ordinary expiry.
     */
    @PostMapping("/sessions/refresh")
    public ResponseEntity<?> refresh(@RequestHeader(value = "Cookie", required = false) String cookieHeader,
                                     @RequestHeader(value = "X-Elmos-Csrf", required = false) String csrfHeader,
                                     HttpServletRequest servletRequest,
                                     @RequestHeader(value = "User-Agent", required = false) String userAgent) {
        if (!SessionCookies.allowStateChange("POST", cookieHeader, csrfHeader)) {
            return error(HttpStatus.FORBIDDEN, "ELMOS_AUTH_CSRF_REQUIRED");
        }
        Optional<String> token = SessionCookies.read(cookieHeader, SessionCookies.REFRESH_COOKIE);
        if (token.isEmpty()) {
            return error(HttpStatus.UNAUTHORIZED, "ELMOS_AUTH_NO_SESSION");
        }

        AuthenticationService.RefreshOutcome outcome = authentication.refresh(
                token.get(), servletRequest.getRemoteAddr(), SessionCookies.clientFamily(userAgent));

        return switch (outcome.status()) {
            case ROTATED -> issueSession(outcome.session(), "REFRESHED");
            case REUSE_DETECTED -> ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("status", "ERROR", "code", "ELMOS_AUTH_SESSION_REVOKED",
                            "reason", "REFRESH_TOKEN_REUSED"));
            case REJECTED -> error(HttpStatus.UNAUTHORIZED, "ELMOS_AUTH_NO_SESSION");
        };
    }

    @PostMapping("/sessions/logout")
    public ResponseEntity<?> logout(@RequestHeader(value = "Cookie", required = false) String cookieHeader,
                                    @RequestHeader(value = "X-Elmos-Csrf", required = false) String csrfHeader) {
        if (!SessionCookies.allowStateChange("POST", cookieHeader, csrfHeader)) {
            return error(HttpStatus.FORBIDDEN, "ELMOS_AUTH_CSRF_REQUIRED");
        }
        SessionCookies.read(cookieHeader, SessionCookies.REFRESH_COOKIE)
                .ifPresent(authentication::signOut);
        // The cookie is cleared whether or not a session existed, so a stale tab
        // cannot be left holding one.
        return ResponseEntity.status(HttpStatus.OK)
                .header(HttpHeaders.SET_COOKIE, SessionCookies.clearedRefreshCookie())
                .header(HttpHeaders.SET_COOKIE, SessionCookies.clearedCsrfCookie())
                .body(Map.of("status", "SIGNED_OUT"));
    }

    // ---- organization switching -------------------------------------------

    public record SwitchRequest(String organizationId) {
    }

    @PostMapping("/organizations/switch")
    public ResponseEntity<?> switchOrganization(@RequestBody SwitchRequest request,
                                                @RequestHeader(value = "Cookie", required = false) String cookieHeader,
                                                @RequestHeader(value = "X-Elmos-Csrf", required = false) String csrfHeader) {
        if (!SessionCookies.allowStateChange("POST", cookieHeader, csrfHeader)) {
            return error(HttpStatus.FORBIDDEN, "ELMOS_AUTH_CSRF_REQUIRED");
        }
        Optional<String> token = SessionCookies.read(cookieHeader, SessionCookies.REFRESH_COOKIE);
        if (token.isEmpty()) {
            return error(HttpStatus.UNAUTHORIZED, "ELMOS_AUTH_NO_SESSION");
        }
        // Rotating on switch keeps one rule for the whole surface: every
        // state-changing session call moves the token forward.
        AuthenticationService.RefreshOutcome refreshed = authentication.refresh(token.get(), null, null);
        if (refreshed.status() != AuthenticationService.RefreshStatus.ROTATED) {
            return error(HttpStatus.UNAUTHORIZED, "ELMOS_AUTH_NO_SESSION");
        }

        Optional<AuthenticationService.Session> switched = authentication.switchOrganization(
                refreshed.session(), request.organizationId());
        if (switched.isEmpty()) {
            // 404, not 403: a caller must not learn that an organization exists but
            // is not theirs.
            return error(HttpStatus.NOT_FOUND, "ELMOS_ORGANIZATION_UNKNOWN");
        }
        return issueSession(switched.get(), "SWITCHED");
    }

    // ---- helpers -----------------------------------------------------------

    /**
     * Builds the response for a newly issued or rotated session.
     *
     * <p>Two invariants: the refresh token appears only in a Set-Cookie header,
     * never in the JSON; and a fresh CSRF value is minted alongside it so the two
     * halves of the double submit always rotate together.</p>
     */
    private ResponseEntity<?> issueSession(AuthenticationService.Session session, String status) {
        String csrf = Secrets.newOpaqueToken();
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", status);
        body.put("accountId", session.accountId());
        body.put("organizationId", session.organizationId());
        body.put("memberships", session.memberships().stream()
                .map(membership -> Map.of(
                        "organizationId", membership.organizationId(),
                        "displayName", membership.displayName(),
                        "role", membership.role()))
                .toList());
        return ResponseEntity.status(HttpStatus.OK)
                .header(
                        HttpHeaders.SET_COOKIE,
                        SessionCookies.refreshCookie(
                                session.refreshToken(), session.idleLifetime()))
                .header(
                        HttpHeaders.SET_COOKIE,
                        SessionCookies.csrfCookie(csrf, session.idleLifetime()))
                .body(body);
    }

    private static ResponseEntity<?> error(HttpStatus status, String code) {
        return ResponseEntity.status(status).body(Map.of("status", "ERROR", "code", code));
    }

    private static Destinations.Channel parseChannel(String value) {
        try {
            return value == null ? null : Destinations.Channel.valueOf(value);
        } catch (IllegalArgumentException ex) {
            return null;
        }
    }

    private static AuthenticationService.Purpose parsePurpose(String value) {
        try {
            return value == null ? null : AuthenticationService.Purpose.valueOf(value);
        } catch (IllegalArgumentException ex) {
            return null;
        }
    }

    @ExceptionHandler(IdentityStore.StoreException.class)
    public ResponseEntity<?> onStoreFailure(IdentityStore.StoreException ex) {
        HttpStatus status = switch (ex.code()) {
            case "ELMOS_CHALLENGE_TOO_FREQUENT", "ELMOS_CHALLENGE_DAILY_LIMIT",
                 "ELMOS_CHALLENGE_CLIENT_LIMIT" -> HttpStatus.TOO_MANY_REQUESTS;
            case "ELMOS_MESSAGE_PROVIDER_NOT_CONFIGURED" -> HttpStatus.SERVICE_UNAVAILABLE;
            case "ELMOS_IDENTITY_CONFLICT" -> HttpStatus.CONFLICT;
            default -> HttpStatus.BAD_GATEWAY;
        };
        return error(status, ex.code());
    }

    /** Unused; kept so the duration constant has one home if the front end asks for it. */
    static Duration defaultIdleLifetime() {
        return Duration.ofDays(14);
    }
}
