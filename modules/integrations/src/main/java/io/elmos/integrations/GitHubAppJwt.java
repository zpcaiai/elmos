package io.elmos.integrations;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.security.PrivateKey;
import java.security.Signature;
import java.time.Clock;
import java.util.Base64;
import java.util.Map;
import java.util.Objects;

public final class GitHubAppJwt {
    private static final Base64.Encoder URL = Base64.getUrlEncoder().withoutPadding();
    private final String issuer; private final PrivateKey privateKey; private final Clock clock; private final ObjectMapper mapper;
    public GitHubAppJwt(String issuer, PrivateKey privateKey, Clock clock, ObjectMapper mapper) {
        if (issuer == null || issuer.isBlank()) throw new IllegalArgumentException("GitHub App issuer is required");
        this.issuer = issuer; this.privateKey = Objects.requireNonNull(privateKey); this.clock = Objects.requireNonNull(clock); this.mapper = Objects.requireNonNull(mapper);
    }
    public String create() {
        try {
            long now = clock.instant().getEpochSecond();
            String header = URL.encodeToString(mapper.writeValueAsBytes(Map.of("alg", "RS256", "typ", "JWT")));
            String payload = URL.encodeToString(mapper.writeValueAsBytes(Map.of("iat", now - 60, "exp", now + 540, "iss", issuer)));
            String signingInput = header + "." + payload;
            Signature signature = Signature.getInstance("SHA256withRSA"); signature.initSign(privateKey);
            signature.update(signingInput.getBytes(StandardCharsets.US_ASCII));
            return signingInput + "." + URL.encodeToString(signature.sign());
        } catch (Exception exception) { throw new IllegalStateException("unable to sign GitHub App JWT", exception); }
    }
}
