package io.elmos.worker;

import io.elmos.security.FileNonceStore;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.HexFormat;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class SpringEngineRequestAuthenticationFilterTest {
    private static final Instant NOW = Instant.parse("2026-09-04T08:00:00Z");
    private static final byte[] SECRET = "spring-engine-ingress-test-secret-000000000000".getBytes(StandardCharsets.UTF_8);
    private static final String PATH = "/engine/v1/spring-upgrades";
    private static final String ORGANIZATION = "org-production-a";
    private static final String ACTOR = "user:operator-a";

    @TempDir
    Path temporary;

    @Test
    void acceptsOneSignedRequestAndPreservesTheRequestBody() throws Exception {
        byte[] body = "{\"organizationId\":\"org-production-a\"}".getBytes(StandardCharsets.UTF_8);
        var authentication = authentication();
        var filter = new SpringEngineRequestAuthenticationFilter(true, authentication);
        MockHttpServletRequest request = signedRequest(authentication, body, UUID.randomUUID().toString());
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<byte[]> observed = new AtomicReference<>();

        filter.doFilter(request, response, (candidate, ignored) ->
                observed.set(candidate.getInputStream().readAllBytes()));

        assertEquals(200, response.getStatus());
        assertArrayEquals(body, observed.get());
    }

    @Test
    void authenticatesTheCanonicalApplicationPathBehindContextAndServletPrefixes() throws Exception {
        byte[] body = "{\"organizationId\":\"org-production-a\"}".getBytes(StandardCharsets.UTF_8);
        var authentication = authentication();
        var filter = new SpringEngineRequestAuthenticationFilter(true, authentication);
        MockHttpServletRequest request = signedRequest(authentication, body, UUID.randomUUID().toString());
        request.setRequestURI("/elmos/internal" + PATH);
        request.setContextPath("/elmos");
        request.setServletPath("/internal");
        request.setPathInfo(PATH);
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<Boolean> invoked = new AtomicReference<>(false);

        filter.doFilter(request, response, (candidate, ignored) -> invoked.set(true));

        assertTrue(invoked.get());
        assertEquals(200, response.getStatus());
    }

    @Test
    void contextPrefixCannotHideAnUnsignedProtectedRoute() throws Exception {
        var filter = new SpringEngineRequestAuthenticationFilter(true, authentication());
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/elmos" + PATH);
        request.setContextPath("/elmos");
        request.setServletPath(PATH);

        assertRejectedBeforeController(filter, request);
    }

    @Test
    void servletPrefixCannotHideAnUnsignedProtectedRoute() throws Exception {
        var filter = new SpringEngineRequestAuthenticationFilter(true, authentication());
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/internal" + PATH);
        request.setServletPath("/internal");
        request.setPathInfo(PATH);

        assertRejectedBeforeController(filter, request);
    }

    @Test
    void rejectsEncodedAndMatrixParameterPathAmbiguity() throws Exception {
        var filter = new SpringEngineRequestAuthenticationFilter(true, authentication());

        assertRejectedBeforeController(filter, new MockHttpServletRequest(
                "POST", "/%65ngine/v1/spring-upgrades"));
        assertRejectedBeforeController(filter, new MockHttpServletRequest(
                "POST", PATH + ";jsessionid=attacker"));
        assertRejectedBeforeController(filter, new MockHttpServletRequest(
                "POST", PATH + "%2F00000000-0000-4000-8000-000000000001/cancel"));
    }

    @Test
    void rejectsInconsistentContainerPathMetadata() throws Exception {
        var filter = new SpringEngineRequestAuthenticationFilter(true, authentication());
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/public" + PATH);
        request.setContextPath("/elmos");
        request.setServletPath(PATH);

        assertRejectedBeforeController(filter, request);
    }

    @Test
    void rejectsTamperedBodiesAndDoesNotInvokeTheController() throws Exception {
        byte[] original = "{\"organizationId\":\"org-production-a\"}".getBytes(StandardCharsets.UTF_8);
        var authentication = authentication();
        var filter = new SpringEngineRequestAuthenticationFilter(true, authentication);
        MockHttpServletRequest request = signedRequest(authentication, original, UUID.randomUUID().toString());
        request.setContent("{\"organizationId\":\"org-attacker\"}".getBytes(StandardCharsets.UTF_8));
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<Boolean> invoked = new AtomicReference<>(false);

        filter.doFilter(request, response, (candidate, ignored) -> invoked.set(true));

        assertEquals(401, response.getStatus());
        assertFalse(invoked.get());
        assertTrue(response.getContentAsString().contains("SPRING_ENGINE_AUTHENTICATION_REQUIRED"));
    }

    @Test
    void rejectsAReplayEvenWhenEverySignedByteIsIdentical() throws Exception {
        byte[] body = "{}".getBytes(StandardCharsets.UTF_8);
        String nonce = UUID.randomUUID().toString();
        var authentication = authentication();
        var filter = new SpringEngineRequestAuthenticationFilter(true, authentication);
        MockHttpServletRequest first = signedRequest(authentication, body, nonce);
        MockHttpServletRequest replay = signedRequest(authentication, body, nonce);

        filter.doFilter(first, new MockHttpServletResponse(), (candidate, ignored) -> { });
        MockHttpServletResponse rejected = new MockHttpServletResponse();
        filter.doFilter(replay, rejected, (candidate, ignored) -> fail("replay reached controller"));

        assertEquals(401, rejected.getStatus());
    }

    @Test
    void invalidSignatureDoesNotConsumeNonceAndReplaySurvivesRestart() throws Exception {
        byte[] body = "{}".getBytes(StandardCharsets.UTF_8);
        Path replayRoot = temporary.toRealPath().resolve("persistent-replay");
        var first = authentication(replayRoot);
        String timestamp = Long.toString(NOW.getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String bodySha = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));

        assertThrows(RuntimeException.class, () -> first.verify(
                timestamp,
                nonce,
                bodySha,
                "0".repeat(64),
                "POST",
                PATH,
                ORGANIZATION,
                ACTOR,
                body));

        String signature = SpringEngineRequestAuthenticationFilter.Authentication.sign(
                SECRET, timestamp, nonce, "POST", PATH, ORGANIZATION, ACTOR, bodySha);
        first.verify(
                timestamp, nonce, bodySha, signature, "POST", PATH, ORGANIZATION, ACTOR, body);

        var restarted = authentication(replayRoot);
        assertThrows(RuntimeException.class, () -> restarted.verify(
                timestamp,
                nonce,
                bodySha,
                signature,
                "POST",
                PATH,
                ORGANIZATION,
                ACTOR,
                body));
    }

    @Test
    void rejectsSignedButUnsupportedPathsAndOverflowTimestamps() throws Exception {
        byte[] body = "{}".getBytes(StandardCharsets.UTF_8);
        String bodySha = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
        var authentication = authentication();

        String traversalPath = PATH + "/run/../artifact";
        String timestamp = Long.toString(NOW.getEpochSecond());
        String traversalNonce = UUID.randomUUID().toString();
        String traversalSignature = SpringEngineRequestAuthenticationFilter.Authentication.sign(
                SECRET, timestamp, traversalNonce, "POST", traversalPath,
                ORGANIZATION, ACTOR, bodySha);
        assertThrows(RuntimeException.class, () -> authentication.verify(
                timestamp,
                traversalNonce,
                bodySha,
                traversalSignature,
                "POST",
                traversalPath,
                ORGANIZATION,
                ACTOR,
                body));

        String extreme = Long.toString(Long.MIN_VALUE);
        String extremeNonce = UUID.randomUUID().toString();
        String extremeSignature = SpringEngineRequestAuthenticationFilter.Authentication.sign(
                SECRET, extreme, extremeNonce, "POST", PATH, ORGANIZATION, ACTOR, bodySha);
        assertThrows(RuntimeException.class, () -> authentication.verify(
                extreme, extremeNonce, bodySha, extremeSignature, "POST", PATH,
                ORGANIZATION, ACTOR, body));
    }

    @Test
    void pastFreshnessBoundaryRemainsValidWhenClockTicksBeforeNonceClaim() throws Exception {
        Clock clock = advancesAfterFirstRead();
        var authentication = new SpringEngineRequestAuthenticationFilter.Authentication(
                SECRET,
                clock,
                60,
                new FileNonceStore(
                        temporary.toRealPath().resolve("boundary-replay"), clock));
        byte[] body = "{}".getBytes(StandardCharsets.UTF_8);
        String bodySha = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
        String timestamp = Long.toString(NOW.minusSeconds(60).getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = SpringEngineRequestAuthenticationFilter.Authentication.sign(
                SECRET, timestamp, nonce, "POST", PATH, ORGANIZATION, ACTOR, bodySha);

        assertDoesNotThrow(() -> authentication.verify(
                timestamp, nonce, bodySha, signature, "POST", PATH,
                ORGANIZATION, ACTOR, body));
    }

    @Test
    void readsOnlyExactOwnerOnlyNonLinkedSecretFiles() throws Exception {
        Path directory = temporary.toRealPath();
        Path secret = directory.resolve("secret");
        Files.write(secret, SECRET);
        Files.setPosixFilePermissions(secret, PosixFilePermissions.fromString("rw-------"));
        assertArrayEquals(SECRET, SpringEngineRequestAuthenticationFilter.readSecret(secret));

        Path hardlink = directory.resolve("hardlink");
        Files.createLink(hardlink, secret);
        assertThrows(
                IllegalStateException.class,
                () -> SpringEngineRequestAuthenticationFilter.readSecret(secret));
        Files.delete(hardlink);

        Files.setPosixFilePermissions(secret, PosixFilePermissions.fromString("---------"));
        assertThrows(
                IllegalStateException.class,
                () -> SpringEngineRequestAuthenticationFilter.readSecret(secret));

        Path realParent = directory.resolve("real-parent");
        Files.createDirectory(realParent);
        Path nestedSecret = realParent.resolve("nested-secret");
        Files.write(nestedSecret, SECRET);
        Files.setPosixFilePermissions(
                nestedSecret, PosixFilePermissions.fromString("r--------"));
        Path linkedParent = directory.resolve("linked-parent");
        Files.createSymbolicLink(linkedParent, realParent);
        assertThrows(
                IllegalStateException.class,
                () -> SpringEngineRequestAuthenticationFilter.readSecret(
                        linkedParent.resolve("nested-secret")));
    }

    @Test
    void capabilitiesRemainAReadOnlyUnauthenticatedDiscoveryEndpoint() throws Exception {
        var filter = new SpringEngineRequestAuthenticationFilter(true, authentication());
        MockHttpServletRequest request = new MockHttpServletRequest(
                "GET", "/engine/v1/spring-upgrades/capabilities");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<Boolean> invoked = new AtomicReference<>(false);

        filter.doFilter(request, response, (candidate, ignored) -> invoked.set(true));

        assertTrue(invoked.get());
        assertEquals(200, response.getStatus());
    }

    @Test
    void aDisabledEngineeringBoundaryDoesNotRequireProductionCredentials() throws Exception {
        var filter = new SpringEngineRequestAuthenticationFilter(false, null);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", PATH);
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<Boolean> invoked = new AtomicReference<>(false);

        filter.doFilter(request, response, (candidate, ignored) -> invoked.set(true));

        assertTrue(invoked.get());
        assertEquals(200, response.getStatus());
    }

    private SpringEngineRequestAuthenticationFilter.Authentication authentication() {
        try {
            return authentication(temporary.toRealPath().resolve("replay-" + UUID.randomUUID()));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private static SpringEngineRequestAuthenticationFilter.Authentication authentication(
            Path replayRoot
    ) {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        return new SpringEngineRequestAuthenticationFilter.Authentication(
                SECRET, clock, 60, new FileNonceStore(replayRoot, clock));
    }

    private static Clock advancesAfterFirstRead() {
        return new Clock() {
            private int reads;

            @Override public ZoneId getZone() { return ZoneOffset.UTC; }
            @Override public Clock withZone(ZoneId zone) { return this; }
            @Override public Instant instant() {
                return reads++ == 0 ? NOW : NOW.plusSeconds(1);
            }
        };
    }

    private static void assertRejectedBeforeController(
            SpringEngineRequestAuthenticationFilter filter,
            MockHttpServletRequest request
    ) throws Exception {
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<Boolean> invoked = new AtomicReference<>(false);

        filter.doFilter(request, response, (candidate, ignored) -> invoked.set(true));

        assertEquals(401, response.getStatus());
        assertFalse(invoked.get());
        assertTrue(response.getContentAsString().contains("SPRING_ENGINE_AUTHENTICATION_REQUIRED"));
    }

    private static MockHttpServletRequest signedRequest(
            SpringEngineRequestAuthenticationFilter.Authentication authentication,
            byte[] body,
            String nonce
    ) throws Exception {
        String timestamp = Long.toString(NOW.getEpochSecond());
        String bodySha = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body));
        String signature = SpringEngineRequestAuthenticationFilter.Authentication.sign(
                SECRET, timestamp, nonce, "POST", PATH, ORGANIZATION, ACTOR, bodySha);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", PATH);
        request.setContent(body);
        request.addHeader(SpringEngineRequestAuthenticationFilter.TIMESTAMP, timestamp);
        request.addHeader(SpringEngineRequestAuthenticationFilter.NONCE, nonce);
        request.addHeader(SpringEngineRequestAuthenticationFilter.BODY_SHA256, bodySha);
        request.addHeader(SpringEngineRequestAuthenticationFilter.SIGNATURE, signature);
        request.addHeader(SpringEngineRequestAuthenticationFilter.ORGANIZATION, ORGANIZATION);
        request.addHeader(SpringEngineRequestAuthenticationFilter.ACTOR, ACTOR);
        return request;
    }
}
