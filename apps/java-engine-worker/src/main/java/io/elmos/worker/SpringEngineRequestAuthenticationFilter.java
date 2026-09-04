package io.elmos.worker;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import io.elmos.security.FileNonceStore;
import io.elmos.security.SpringHmacProtocol;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Objects;
import java.util.regex.Pattern;

/**
 * Authenticates the Web BFF before tenant headers reach the Spring migration worker.
 *
 * <p>The body digest, method, path, tenant and actor are signed together. A short
 * timestamp window and one-use nonce prevent a captured request from being replayed.
 * This boundary is independent from browser/OIDC authentication: the BFF performs
 * that check and then proves to the worker that the derived identity was not forged
 * by another container on the backend network.</p>
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
final class SpringEngineRequestAuthenticationFilter extends OncePerRequestFilter {
    static final String TIMESTAMP = "X-ELMOS-Engine-Timestamp";
    static final String NONCE = "X-ELMOS-Engine-Nonce";
    static final String BODY_SHA256 = "X-ELMOS-Engine-Body-SHA256";
    static final String SIGNATURE = "X-ELMOS-Engine-Signature";
    static final String ORGANIZATION = "X-ELMOS-Organization-ID";
    static final String ACTOR = "X-ELMOS-Actor-ID";
    private static final int MAX_BODY_BYTES = 64 * 1024;
    private static final int MAX_PATH_CHARACTERS = 2_048;
    private static final String AUTH_PROTOCOL = "ELMOS-SPRING-ENGINE-HMAC-V1";
    private static final String AUTH_ROLE = "ENGINE";
    private static final String AUTH_SIGNER = "WEB_CONSOLE_BFF";
    private static final String ROOT = "/engine/v1/spring-upgrades";
    private static final String RUN_ID = "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
    private static final Pattern REQUEST_PATH = Pattern.compile(
            "^/engine/v1/spring-upgrades(?:/(?:capabilities|" + RUN_ID
                    + "(?:/(?:logs|artifact|retry|cancel|runtime/(?:start|stop)))?))?$"
    );

    private final boolean enabled;
    private final Authentication authentication;

    @Autowired
    SpringEngineRequestAuthenticationFilter(
            @Value("${elmos.worker.spring-upgrade.ingress-auth-enabled:false}") boolean enabled,
            @Value("${elmos.worker.spring-upgrade.ingress-auth-secret-file:}") String secretFile,
            @Value("${elmos.worker.spring-upgrade.ingress-auth-window-seconds:60}") long windowSeconds,
            @Value("${elmos.worker.spring-upgrade.ingress-auth-replay-root:}") String replayRoot,
            Clock clock
    ) {
        this(enabled, enabled
                ? new Authentication(
                        readSecret(Path.of(secretFile)),
                        clock,
                        windowSeconds,
                        new FileNonceStore(replayRoot(replayRoot), clock))
                : null);
    }

    SpringEngineRequestAuthenticationFilter(boolean enabled, Authentication authentication) {
        this.enabled = enabled;
        this.authentication = authentication;
        if (enabled && authentication == null) {
            throw new IllegalArgumentException("Spring engine ingress authentication is enabled without a verifier");
        }
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        if (!enabled) return true;
        try {
            String path = canonicalApplicationPath(request);
            return !protectedPath(path) || ("GET".equals(request.getMethod())
                    && (ROOT + "/capabilities").equals(path));
        } catch (Rejected error) {
            // Encoded, matrix-parameter, prefix-mismatched, or otherwise ambiguous
            // paths must not turn an authentication failure into a filter bypass.
            // Filter every rejected representation and let doFilterInternal fail
            // closed; trying to infer whether a proxy or servlet container might
            // normalize it into a protected route is inherently incomplete.
            return false;
        }
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws IOException, jakarta.servlet.ServletException {
        byte[] body;
        try {
            String requestPath = canonicalApplicationPath(request);
            if (!protectedPath(requestPath)
                    || ("GET".equals(request.getMethod())
                    && (ROOT + "/capabilities").equals(requestPath))) {
                throw new Rejected();
            }
            body = boundedBody(request);
            authentication.verify(
                    request.getHeader(TIMESTAMP),
                    request.getHeader(NONCE),
                    request.getHeader(BODY_SHA256),
                    request.getHeader(SIGNATURE),
                    request.getMethod(),
                    requestPath,
                    request.getHeader(ORGANIZATION),
                    request.getHeader(ACTOR),
                    body);
        } catch (Rejected error) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType("application/json");
            response.setHeader("Cache-Control", "no-store");
            response.getWriter().write(
                    "{\"errorCode\":\"SPRING_ENGINE_AUTHENTICATION_REQUIRED\","
                            + "\"message\":\"Trusted Spring engine request authentication failed.\","
                            + "\"retryable\":false}");
            return;
        }
        chain.doFilter(new CachedBodyRequest(request, body), response);
    }

    /**
     * Resolve the path seen by application controllers without trusting a raw
     * request URI that may still contain a context or servlet mapping prefix.
     * Percent-encoding and matrix parameters are deliberately unsupported at
     * this authentication boundary: decoding them in more than one component
     * would create multiple byte representations for the signed route.
     */
    static String canonicalApplicationPath(HttpServletRequest request) {
        String requestUri = canonicalPathComponent(request.getRequestURI(), false);
        String contextPath = canonicalPathComponent(request.getContextPath(), true);
        String servletPath = canonicalPathComponent(request.getServletPath(), true);
        String pathInfo = request.getPathInfo();
        if (pathInfo != null) pathInfo = canonicalPathComponent(pathInfo, false);

        if (!contextPath.isEmpty()
                && (!requestUri.startsWith(contextPath)
                || (requestUri.length() > contextPath.length()
                && requestUri.charAt(contextPath.length()) != '/'))) {
            throw new Rejected();
        }
        String servletRelative = requestUri.substring(contextPath.length());
        if (servletRelative.isEmpty()) servletRelative = "/";

        String applicationPath;
        if (pathInfo != null) {
            if (!(servletPath + pathInfo).equals(servletRelative)) throw new Rejected();
            applicationPath = pathInfo;
        } else if (!servletPath.isEmpty()) {
            if (!servletPath.equals(servletRelative)) throw new Rejected();
            applicationPath = servletPath;
        } else {
            applicationPath = servletRelative;
        }
        return canonicalPathComponent(applicationPath, false);
    }

    private static String canonicalPathComponent(String value, boolean emptyAllowed) {
        if (value == null || value.length() > MAX_PATH_CHARACTERS
                || (!emptyAllowed && value.isEmpty())) {
            throw new Rejected();
        }
        if (value.isEmpty()) return value;
        if (value.charAt(0) != '/' || value.indexOf('%') >= 0 || value.indexOf(';') >= 0
                || value.indexOf('\\') >= 0 || value.indexOf('?') >= 0
                || value.indexOf('#') >= 0 || value.contains("//")) {
            throw new Rejected();
        }
        String[] segments = value.substring(1).split("/", -1);
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            if (character <= 0x20 || character >= 0x7f) throw new Rejected();
        }
        for (String segment : segments) {
            if (".".equals(segment) || "..".equals(segment)) throw new Rejected();
        }
        return value;
    }

    private static boolean protectedPath(String path) {
        return ROOT.equals(path) || path.startsWith(ROOT + "/");
    }

    private static byte[] boundedBody(HttpServletRequest request) {
        try {
            if (request.getContentLengthLong() > MAX_BODY_BYTES) throw new Rejected();
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[8 * 1024];
            int count;
            while ((count = request.getInputStream().read(buffer)) >= 0) {
                if (output.size() + count > MAX_BODY_BYTES) throw new Rejected();
                output.write(buffer, 0, count);
            }
            return output.toByteArray();
        } catch (IOException error) {
            throw new Rejected();
        }
    }

    static byte[] readSecret(Path path) {
        return SpringHmacProtocol.readSecret(path, "Spring engine ingress");
    }

    private static Path replayRoot(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Spring engine ingress persistent replay root is required");
        }
        return Path.of(value);
    }

    static final class Authentication {
        private final byte[] secret;
        private final Clock clock;
        private final long windowSeconds;
        private final FileNonceStore nonces;

        Authentication(
                byte[] secret,
                Clock clock,
                long windowSeconds,
                FileNonceStore nonces
        ) {
            this.secret = SpringHmacProtocol.requireSecret(secret, "Spring engine ingress");
            this.clock = Objects.requireNonNull(clock);
            this.windowSeconds = windowSeconds;
            this.nonces = Objects.requireNonNull(nonces);
            if (secret.length < 32 || secret.length > 4_096 || windowSeconds < 30 || windowSeconds > 300) {
                throw new IllegalArgumentException("Spring engine ingress authentication configuration is invalid");
            }
        }

        void verify(
                String timestampValue,
                String nonce,
                String bodySha256,
                String signature,
                String method,
                String requestPath,
                String organizationId,
                String actorId,
                byte[] body
        ) {
            long now = clock.instant().getEpochSecond();
            long timestamp;
            if (!SpringHmacProtocol.isCanonicalTimestamp(timestampValue)) {
                throw new Rejected();
            }
            try {
                timestamp = Long.parseLong(timestampValue);
            } catch (NumberFormatException error) {
                throw new Rejected();
            }
            String observedBodySha = sha256(body);
            if (timestamp < now - windowSeconds || timestamp > now + windowSeconds
                    || !SpringHmacProtocol.isCanonicalNonce(nonce)
                    || signature == null || !signature.matches("[0-9a-f]{64}")
                    || bodySha256 == null || !bodySha256.equals(observedBodySha)
                    || !("GET".equals(method) || "POST".equals(method))
                    || requestPath == null || !REQUEST_PATH.matcher(requestPath).matches()
                    || organizationId == null || !organizationId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
                    || actorId == null || !actorId.matches("[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}")) {
                throw new Rejected();
            }
            String expected = sign(secret, timestampValue, nonce, method, requestPath,
                    organizationId, actorId, bodySha256);
            if (!MessageDigest.isEqual(
                    expected.getBytes(StandardCharsets.US_ASCII),
                    signature.getBytes(StandardCharsets.US_ASCII))) {
                throw new Rejected();
            }
            boolean claimed;
            try {
                long expiry = Math.addExact(Math.max(now, timestamp), windowSeconds);
                claimed = nonces.claim(
                        AUTH_PROTOCOL,
                        AUTH_ROLE,
                        AUTH_SIGNER,
                        nonce,
                        Instant.ofEpochSecond(expiry));
            } catch (RuntimeException error) {
                throw new Rejected();
            }
            if (!claimed) {
                throw new Rejected();
            }
        }

        static String sign(
                byte[] secret,
                String timestamp,
                String nonce,
                String method,
                String requestPath,
                String organizationId,
                String actorId,
                String bodySha256
        ) {
            try {
                String canonical = String.join("\n",
                        AUTH_PROTOCOL,
                        AUTH_ROLE,
                        timestamp,
                        nonce,
                        method,
                        requestPath,
                        organizationId,
                        actorId,
                        bodySha256);
                Mac mac = Mac.getInstance("HmacSHA256");
                mac.init(new SecretKeySpec(secret, "HmacSHA256"));
                return HexFormat.of().formatHex(mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8)));
            } catch (Exception error) {
                throw new IllegalStateException("Spring engine request signing is unavailable", error);
            }
        }

        private static String sha256(byte[] value) {
            try {
                return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
            } catch (Exception error) {
                throw new IllegalStateException("SHA-256 unavailable", error);
            }
        }
    }

    private static final class CachedBodyRequest extends HttpServletRequestWrapper {
        private final byte[] body;

        private CachedBodyRequest(HttpServletRequest request, byte[] body) {
            super(request);
            this.body = body.clone();
        }

        @Override public ServletInputStream getInputStream() {
            ByteArrayInputStream input = new ByteArrayInputStream(body);
            return new ServletInputStream() {
                @Override public boolean isFinished() { return input.available() == 0; }
                @Override public boolean isReady() { return true; }
                @Override public void setReadListener(ReadListener listener) { /* synchronous request body */ }
                @Override public int read() { return input.read(); }
                @Override public int read(byte[] bytes, int offset, int length) { return input.read(bytes, offset, length); }
            };
        }
    }

    private static final class Rejected extends RuntimeException {}
}
