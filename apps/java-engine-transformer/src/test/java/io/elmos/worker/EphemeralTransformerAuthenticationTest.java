package io.elmos.worker;

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

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assertions.assertThrows;

class EphemeralTransformerAuthenticationTest {
    private static final byte[] SECRET =
            "transformer-auth-test-secret-0123456789abcdef".getBytes(StandardCharsets.UTF_8);
    private static final byte[] BODY = "{\"action\":\"TRANSFORM\"}".getBytes(StandardCharsets.UTF_8);
    private static final Instant NOW = Instant.parse("2026-09-05T00:00:00Z");

    @TempDir
    Path temporary;

    @Test
    void persistsReplayStateAcrossAuthenticationRestarts() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        Path root = temporary.toRealPath().resolve("replay");
        EphemeralTransformerAuthentication first = authentication(root, clock);
        String timestamp = Long.toString(NOW.getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = EphemeralTransformerAuthentication.sign(
                SECRET, timestamp, nonce, BODY);

        first.verify(timestamp, nonce, signature, BODY);

        assertThatThrownBy(() -> authentication(root, clock)
                .verify(timestamp, nonce, signature, BODY))
                .isInstanceOf(EphemeralTransformerController.Rejected.class);
    }

    @Test
    void invalidAndCrossRoleSignaturesDoNotConsumeNonce() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        EphemeralTransformerAuthentication authentication = authentication(
                temporary.toRealPath().resolve("poison-replay"), clock);
        String timestamp = Long.toString(NOW.getEpochSecond());

        String invalidNonce = UUID.randomUUID().toString();
        assertThatThrownBy(() -> authentication.verify(
                timestamp, invalidNonce, "0".repeat(64), BODY))
                .isInstanceOf(EphemeralTransformerController.Rejected.class);
        authentication.verify(
                timestamp,
                invalidNonce,
                EphemeralTransformerAuthentication.sign(
                        SECRET, timestamp, invalidNonce, BODY),
                BODY);

        String crossRoleNonce = UUID.randomUUID().toString();
        String verifierSignature = SpringHmacProtocol.sign(
                SECRET,
                SpringHmacProtocol.Role.VERIFIER,
                timestamp,
                crossRoleNonce,
                BODY);
        assertThatThrownBy(() -> authentication.verify(
                timestamp, crossRoleNonce, verifierSignature, BODY))
                .isInstanceOf(EphemeralTransformerController.Rejected.class);
        authentication.verify(
                timestamp,
                crossRoleNonce,
                EphemeralTransformerAuthentication.sign(
                        SECRET, timestamp, crossRoleNonce, BODY),
                BODY);
    }

    @Test
    void rejectsOverflowTimestampExtremes() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        EphemeralTransformerAuthentication authentication = authentication(
                temporary.toRealPath().resolve("overflow-replay"), clock);
        for (String timestamp : new String[]{
                Long.toString(Long.MIN_VALUE), Long.toString(Long.MAX_VALUE)}) {
            assertThatThrownBy(() -> authentication.verify(
                    timestamp, UUID.randomUUID().toString(), "0".repeat(64), BODY))
                    .isInstanceOf(EphemeralTransformerController.Rejected.class);
        }
    }

    @Test
    void unauthorizedAuthenticationMapsToHttp401() {
        assertThat(EphemeralTransformerController.rejectionStatus(
                new EphemeralTransformerController.Rejected(
                        "UNAUTHORIZED", "authentication failed")))
                .isEqualTo(org.springframework.http.HttpStatus.UNAUTHORIZED);
    }

    @Test
    void malformedNonceAndSignedTimestampAreRejectedAsHttp401() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        EphemeralTransformerAuthentication authentication = authentication(
                temporary.toRealPath().resolve("malformed-replay"), clock);
        for (String[] values : new String[][]{
                {Long.toString(NOW.getEpochSecond()), "------------------------------------"},
                {"+" + NOW.getEpochSecond(), UUID.randomUUID().toString()}}) {
            EphemeralTransformerController.Rejected error = assertThrows(
                    EphemeralTransformerController.Rejected.class,
                    () -> authentication.verify(values[0], values[1], "0".repeat(64), BODY));
            assertThat(EphemeralTransformerController.rejectionStatus(error))
                    .isEqualTo(org.springframework.http.HttpStatus.UNAUTHORIZED);
        }
    }

    @Test
    void pastFreshnessBoundaryRemainsValidWhenClockTicksBeforeNonceClaim() throws Exception {
        Clock clock = advancesAfterFirstRead();
        EphemeralTransformerAuthentication authentication = authentication(
                temporary.toRealPath().resolve("boundary-replay"), clock);
        String timestamp = Long.toString(NOW.minusSeconds(90).getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = EphemeralTransformerAuthentication.sign(
                SECRET, timestamp, nonce, BODY);

        authentication.verify(timestamp, nonce, signature, BODY);
    }

    private static EphemeralTransformerAuthentication authentication(
            Path root,
            Clock clock
    ) {
        return new EphemeralTransformerAuthentication(
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
