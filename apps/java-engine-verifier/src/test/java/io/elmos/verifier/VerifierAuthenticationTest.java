package io.elmos.verifier;

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

class VerifierAuthenticationTest {
    private static final byte[] SECRET =
            "verifier-auth-test-secret-0123456789abcdef".getBytes(StandardCharsets.UTF_8);
    private static final byte[] BODY = "{\"runId\":\"run-1\"}".getBytes(StandardCharsets.UTF_8);
    private static final Instant NOW = Instant.parse("2026-09-05T00:00:00Z");

    @TempDir
    Path temporary;

    @Test
    void persistsReplayStateAcrossAuthenticationRestarts() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        Path root = temporary.toRealPath().resolve("replay");
        VerifierAuthentication first = authentication(root, clock);
        String timestamp = Long.toString(NOW.getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = VerifierAuthentication.sign(SECRET, timestamp, nonce, BODY);

        first.verify(timestamp, nonce, signature, BODY);

        assertThatThrownBy(() -> authentication(root, clock)
                .verify(timestamp, nonce, signature, BODY))
                .isInstanceOf(VerificationModels.Rejected.class);
    }

    @Test
    void invalidAndCrossRoleSignaturesDoNotConsumeNonce() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        VerifierAuthentication authentication = authentication(
                temporary.toRealPath().resolve("poison-replay"), clock);
        String timestamp = Long.toString(NOW.getEpochSecond());

        String invalidNonce = UUID.randomUUID().toString();
        assertThatThrownBy(() -> authentication.verify(
                timestamp, invalidNonce, "0".repeat(64), BODY))
                .isInstanceOf(VerificationModels.Rejected.class);
        authentication.verify(
                timestamp,
                invalidNonce,
                VerifierAuthentication.sign(SECRET, timestamp, invalidNonce, BODY),
                BODY);

        String crossRoleNonce = UUID.randomUUID().toString();
        String transformerSignature = SpringHmacProtocol.sign(
                SECRET,
                SpringHmacProtocol.Role.TRANSFORMER,
                timestamp,
                crossRoleNonce,
                BODY);
        assertThatThrownBy(() -> authentication.verify(
                timestamp, crossRoleNonce, transformerSignature, BODY))
                .isInstanceOf(VerificationModels.Rejected.class);
        authentication.verify(
                timestamp,
                crossRoleNonce,
                VerifierAuthentication.sign(SECRET, timestamp, crossRoleNonce, BODY),
                BODY);
    }

    @Test
    void rejectsOverflowTimestampExtremes() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        VerifierAuthentication authentication = authentication(
                temporary.toRealPath().resolve("overflow-replay"), clock);
        for (String timestamp : new String[]{
                Long.toString(Long.MIN_VALUE), Long.toString(Long.MAX_VALUE)}) {
            assertThatThrownBy(() -> authentication.verify(
                    timestamp, UUID.randomUUID().toString(), "0".repeat(64), BODY))
                    .isInstanceOf(VerificationModels.Rejected.class);
        }
    }

    @Test
    void rejectsMalformedNonceAndSignedTimestampWithoutCallingCanonicalSigner() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        VerifierAuthentication authentication = authentication(
                temporary.toRealPath().resolve("malformed-replay"), clock);
        for (String[] values : new String[][]{
                {Long.toString(NOW.getEpochSecond()), "------------------------------------"},
                {"+" + NOW.getEpochSecond(), UUID.randomUUID().toString()}}) {
            assertThatThrownBy(() -> authentication.verify(
                    values[0], values[1], "0".repeat(64), BODY))
                    .isInstanceOf(VerificationModels.Rejected.class);
        }
    }

    @Test
    void pastFreshnessBoundaryRemainsValidWhenClockTicksBeforeNonceClaim() throws Exception {
        Clock clock = advancesAfterFirstRead();
        VerifierAuthentication authentication = authentication(
                temporary.toRealPath().resolve("boundary-replay"), clock);
        String timestamp = Long.toString(NOW.minusSeconds(90).getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = VerifierAuthentication.sign(SECRET, timestamp, nonce, BODY);

        assertThatCode(() -> authentication.verify(timestamp, nonce, signature, BODY))
                .doesNotThrowAnyException();
    }

    private static VerifierAuthentication authentication(Path root, Clock clock) {
        return new VerifierAuthentication(
                SECRET, clock, 90, new FileNonceStore(root, clock));
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
