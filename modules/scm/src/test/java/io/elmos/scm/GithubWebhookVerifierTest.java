package io.elmos.scm;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class GithubWebhookVerifierTest {
    private static final char[] SECRET = "It's a Secret to Everybody".toCharArray();
    private static final String SIGNATURE = "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17";

    @Test void verifiesGithubPublishedVectorAndRejectsMutation() {
        GithubWebhookVerifier verifier = new GithubWebhookVerifier();
        assertTrue(verifier.verify("Hello, World!".getBytes(StandardCharsets.UTF_8), SIGNATURE, List.of(SECRET)));
        assertFalse(verifier.verify("Hello, world!".getBytes(StandardCharsets.UTF_8), SIGNATURE, List.of(SECRET)));
        assertFalse(verifier.verify("Hello, World!".getBytes(StandardCharsets.UTF_8), "sha256=bad", List.of(SECRET)));
    }

    @Test void deduplicatesBeforeEnqueueAndRejectsInvalidSignature() throws Exception {
        byte[] body = "{\"action\":\"created\",\"repository\":{\"id\":7},\"installation\":{\"id\":9}}".getBytes(StandardCharsets.UTF_8);
        String signature = hmac(body);
        AtomicInteger stores = new AtomicInteger();
        WebhookIngestionService service = new WebhookIngestionService(new GithubWebhookVerifier(),
                ignored -> stores.incrementAndGet() == 1, new ObjectMapper(),
                Clock.fixed(Instant.parse("2026-07-20T00:00:00Z"), ZoneOffset.UTC), 1024 * 1024);
        assertEquals(WebhookIngestionService.Result.ACCEPTED, service.ingest("delivery-1", "installation_repositories", signature, body, List.of(SECRET)));
        assertEquals(WebhookIngestionService.Result.DUPLICATE, service.ingest("delivery-1", "installation_repositories", signature, body, List.of(SECRET)));
        assertThrows(SecurityException.class, () -> service.ingest("delivery-2", "push", SIGNATURE, body, List.of(SECRET)));
        assertEquals(2, stores.get());
    }

    private static String hmac(byte[] body) throws Exception {
        javax.crypto.Mac mac = javax.crypto.Mac.getInstance("HmacSHA256");
        mac.init(new javax.crypto.spec.SecretKeySpec(new String(SECRET).getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return "sha256=" + java.util.HexFormat.of().formatHex(mac.doFinal(body));
    }
}
