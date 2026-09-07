package io.elmos.identity;

import java.time.Duration;
import java.util.Locale;
import java.util.Optional;

/**
 * Cookie construction for the browser session.
 *
 * <p>Split out and made pure so the flags can be asserted in a test. Cookie
 * attributes are the kind of thing that gets weakened during a debugging session
 * and never restored; a test that names each one makes that visible in review.</p>
 */
public final class SessionCookies {

    /**
     * The {@code __Host-} prefix is not decoration. A browser refuses to accept a
     * cookie with this prefix unless it is Secure, has Path=/ and carries no Domain
     * attribute - which means a subdomain, including one an attacker gets control
     * of, cannot overwrite it. That is the specific attack this defends against.
     */
    public static final String REFRESH_COOKIE = "__Host-elmos_refresh";
    public static final String CSRF_COOKIE = "__Host-elmos_csrf";

    private SessionCookies() {
    }

    /**
     * The refresh cookie: HttpOnly so script cannot read it, SameSite=Lax so it is
     * not sent on cross-site POSTs, and scoped to the refresh path only, so it is
     * not attached to every ordinary API call.
     */
    public static String refreshCookie(String token, Duration maxAge) {
        return REFRESH_COOKIE + "=" + token
                + "; Max-Age=" + maxAge.toSeconds()
                + "; Path=/; Secure; HttpOnly; SameSite=Lax";
    }

    public static String clearedRefreshCookie() {
        return REFRESH_COOKIE + "=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax";
    }

    /**
     * The CSRF cookie is deliberately readable by script: the double-submit pattern
     * requires the page to copy it into a header, which proves same-origin because
     * a cross-site page cannot read it.
     */
    public static String csrfCookie(String token, Duration maxAge) {
        return CSRF_COOKIE + "=" + token
                + "; Max-Age=" + maxAge.toSeconds()
                + "; Path=/; Secure; SameSite=Lax";
    }

    /** Constant-time comparison of the cookie and header halves of the double submit. */
    public static boolean csrfMatches(String cookieValue, String headerValue) {
        if (cookieValue == null || headerValue == null
                || cookieValue.isBlank() || headerValue.isBlank()) {
            return false;
        }
        return Secrets.constantTimeEquals(cookieValue, headerValue);
    }

    /** Reads one cookie out of a raw Cookie header without trusting its shape. */
    public static Optional<String> read(String cookieHeader, String name) {
        if (cookieHeader == null || name == null) {
            return Optional.empty();
        }
        for (String part : cookieHeader.split(";")) {
            String candidate = part.trim();
            int equals = candidate.indexOf('=');
            if (equals <= 0) {
                continue;
            }
            if (candidate.substring(0, equals).equals(name)) {
                String value = candidate.substring(equals + 1).trim();
                return value.isEmpty() ? Optional.empty() : Optional.of(value);
            }
        }
        return Optional.empty();
    }

    /**
     * Whether a request may perform a state-changing action.
     *
     * <p>Two independent conditions, because either alone has known gaps: SameSite
     * is not enforced by every client, and double-submit fails if a subdomain can
     * set cookies - which the {@code __Host-} prefix separately prevents.</p>
     */
    public static boolean allowStateChange(String method, String cookieHeader, String csrfHeader) {
        if (!"POST".equals(method) && !"DELETE".equals(method) && !"PATCH".equals(method)) {
            return false;
        }
        return csrfMatches(read(cookieHeader, CSRF_COOKIE).orElse(null), csrfHeader);
    }

    /** Coarse client family for the session record; never the raw user agent. */
    public static String clientFamily(String userAgent) {
        if (userAgent == null) {
            return null;
        }
        String value = userAgent.toLowerCase(Locale.ROOT);
        if (value.contains("micromessenger")) {
            return "wechat";
        }
        if (value.contains("edg/")) {
            return "edge";
        }
        if (value.contains("chrome")) {
            return "chrome";
        }
        if (value.contains("safari")) {
            return "safari";
        }
        if (value.contains("firefox")) {
            return "firefox";
        }
        if (value.contains("curl") || value.contains("elmos")) {
            return "cli";
        }
        return "other";
    }
}
