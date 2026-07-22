package io.elmos.integrations;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.time.*;
import java.util.Base64;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class GitHubAppJwtTest {
    @Test void signsShortLivedRs256Jwt() throws Exception {
        var generator = KeyPairGenerator.getInstance("RSA"); generator.initialize(2048); var pair = generator.generateKeyPair();
        Instant now = Instant.parse("2026-07-20T00:00:00Z"); ObjectMapper mapper = new ObjectMapper();
        String jwt = new GitHubAppJwt("client-id", pair.getPrivate(), Clock.fixed(now, ZoneOffset.UTC), mapper).create();
        String[] segments = jwt.split("\\."); assertEquals(3, segments.length);
        @SuppressWarnings("unchecked") Map<String,Object> claims = mapper.readValue(Base64.getUrlDecoder().decode(segments[1]), Map.class);
        assertEquals("client-id", claims.get("iss")); assertEquals(now.getEpochSecond() + 540, ((Number) claims.get("exp")).longValue());
        Signature verifier = Signature.getInstance("SHA256withRSA"); verifier.initVerify(pair.getPublic());
        verifier.update((segments[0] + "." + segments[1]).getBytes(StandardCharsets.US_ASCII));
        assertTrue(verifier.verify(Base64.getUrlDecoder().decode(segments[2])));
    }
}
