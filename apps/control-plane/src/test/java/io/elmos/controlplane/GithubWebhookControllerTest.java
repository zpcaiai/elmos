package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.scm.GithubWebhookVerifier;
import io.elmos.scm.WebhookIngestionService;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GithubWebhookControllerTest {
    @Test void acceptsRawSignedPayload() throws Exception {
        char[] secret = "It's a Secret to Everybody".toCharArray(); byte[] body = "{\"action\":\"created\"}".getBytes(StandardCharsets.UTF_8);
        javax.crypto.Mac mac = javax.crypto.Mac.getInstance("HmacSHA256");
        mac.init(new javax.crypto.spec.SecretKeySpec(new String(secret).getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        String signature = "sha256=" + java.util.HexFormat.of().formatHex(mac.doFinal(body));
        var service = new WebhookIngestionService(new GithubWebhookVerifier(), ignored -> true, new ObjectMapper(), Clock.systemUTC(), 1024);
        var response = new GithubWebhookController(service, () -> List.of(secret.clone())).receive("d-1", "push", signature, body);
        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode()); assertEquals("ACCEPTED", response.getBody().get("status"));
    }

    @Test void rejectsOversizedPayloadBeforeControllerParsing() throws Exception {
        var request = new MockHttpServletRequest("POST", "/api/webhooks/github");
        request.setContent(new byte[9]); var response = new MockHttpServletResponse(); var chain = new MockFilterChain();
        new GithubWebhookBodyLimitFilter(8).doFilter(request, response, chain);
        assertEquals(413, response.getStatus());
    }
}
