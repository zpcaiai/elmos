package io.elmos.workspaceservice;

import io.elmos.security.FileNonceStore;
import io.elmos.security.SpringHmacProtocol;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThatCode;

class SpringRuntimeAuthenticationTest {
    private static final byte[] SECRET =
            "workspace-spring-auth-secret-0123456789abcdef".getBytes(StandardCharsets.UTF_8);
    private static final Instant NOW = Instant.parse("2026-09-05T00:00:00Z");
    private static final byte[] BODY = "{\"action\":\"START\"}".getBytes(StandardCharsets.UTF_8);

    @TempDir
    Path temporary;

    @Test
    void acceptsOnlyItsRoleAndPersistsReplayStateAcrossInstances() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        Path replayRoot = temporary.toRealPath().resolve("runtime-replay");
        SpringRuntimeAuthentication first = authentication(
                SpringHmacProtocol.Role.RUNTIME, replayRoot, clock);
        String timestamp = Long.toString(NOW.getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = SpringRuntimeAuthentication.sign(
                SECRET, SpringHmacProtocol.Role.RUNTIME, timestamp, nonce, BODY);

        first.verify(timestamp, nonce, signature, BODY);

        SpringRuntimeAuthentication restarted = authentication(
                SpringHmacProtocol.Role.RUNTIME, replayRoot, clock);
        assertThatThrownBy(() -> restarted.verify(timestamp, nonce, signature, BODY))
                .isInstanceOf(SpringRuntimeModels.Rejected.class);
    }

    @Test
    void invalidOrCrossRoleSignatureDoesNotConsumeTheNonce() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        SpringRuntimeAuthentication verifier = authentication(
                SpringHmacProtocol.Role.VERIFIER,
                temporary.toRealPath().resolve("verifier-replay"),
                clock);
        String timestamp = Long.toString(NOW.getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String transformerSignature = SpringRuntimeAuthentication.sign(
                SECRET, SpringHmacProtocol.Role.TRANSFORMER, timestamp, nonce, BODY);

        assertThatThrownBy(() -> verifier.verify(timestamp, nonce, transformerSignature, BODY))
                .isInstanceOf(SpringRuntimeModels.Rejected.class);

        String verifierSignature = SpringRuntimeAuthentication.sign(
                SECRET, SpringHmacProtocol.Role.VERIFIER, timestamp, nonce, BODY);
        verifier.verify(timestamp, nonce, verifierSignature, BODY);
    }

    @Test
    void rejectsOverflowTimestampExtremes() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        SpringRuntimeAuthentication runtime = authentication(
                SpringHmacProtocol.Role.RUNTIME,
                temporary.toRealPath().resolve("overflow-replay"),
                clock);
        for (String timestamp : new String[]{
                Long.toString(Long.MIN_VALUE), Long.toString(Long.MAX_VALUE)}) {
            String nonce = UUID.randomUUID().toString();
            assertThatThrownBy(() -> runtime.verify(
                    timestamp, nonce, "0".repeat(64), BODY))
                    .isInstanceOf(SpringRuntimeModels.Rejected.class);
        }
    }

    @Test
    void rejectsMalformedNonceAndSignedTimestampWithoutCallingCanonicalSigner() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        SpringRuntimeAuthentication runtime = authentication(
                SpringHmacProtocol.Role.RUNTIME,
                temporary.toRealPath().resolve("malformed-replay"),
                clock);
        for (String[] values : new String[][]{
                {Long.toString(NOW.getEpochSecond()), "------------------------------------"},
                {"+" + NOW.getEpochSecond(), UUID.randomUUID().toString()}}) {
            assertThatThrownBy(() -> runtime.verify(
                    values[0], values[1], "0".repeat(64), BODY))
                    .isInstanceOf(SpringRuntimeModels.Rejected.class);
        }
    }

    @Test
    void pastFreshnessBoundaryRemainsValidWhenClockTicksBeforeNonceClaim() throws Exception {
        Clock clock = advancesAfterFirstRead();
        SpringRuntimeAuthentication runtime = authentication(
                SpringHmacProtocol.Role.RUNTIME,
                temporary.toRealPath().resolve("boundary-replay"),
                clock);
        String timestamp = Long.toString(NOW.minusSeconds(90).getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = SpringRuntimeAuthentication.sign(
                SECRET, SpringHmacProtocol.Role.RUNTIME, timestamp, nonce, BODY);

        assertThatCode(() -> runtime.verify(timestamp, nonce, signature, BODY))
                .doesNotThrowAnyException();
    }

    private static SpringRuntimeAuthentication authentication(
            SpringHmacProtocol.Role role,
            Path replayRoot,
            Clock clock
    ) {
        return new SpringRuntimeAuthentication(
                SECRET, role, clock, 90, new FileNonceStore(replayRoot, clock));
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
}
