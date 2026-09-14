package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.Base64;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** Exact-byte Ed25519 host envelope; the worker verifies scope registration and replay. */
final class DeploymentHostSigner {
    private final String keyId;
    private final String audience;
    private final PrivateKey key;
    private final Clock clock;
    private final ObjectMapper json;

    DeploymentHostSigner(String keyId, String audience, PrivateKey key, Clock clock, ObjectMapper json) {
        if (!keyId.matches("[A-Za-z0-9_-]{1,64}") || audience.isBlank()) {
            throw new IllegalArgumentException("DEPLOYMENT_SIGNER_CONFIGURATION");
        }
        this.keyId = keyId;
        this.audience = audience;
        this.key = key;
        this.clock = clock;
        this.json = json;
    }

    String sign(String method, String path, byte[] body, String actor,
                Map<String, String> scope, Set<String> permissions) {
        if (!Set.of("GET", "POST").contains(method) || !path.startsWith("/v1/")
                || path.contains("?") || body.length > 65536
                || !scope.keySet().equals(Set.of("tenant_id", "workspace_id", "project_id",
                                               "environment_id", "account_id"))) {
            throw new IllegalArgumentException("DEPLOYMENT_REQUEST_CONTRACT");
        }
        try {
            long now = clock.instant().getEpochSecond();
            Map<String, Object> claim = new LinkedHashMap<>();
            claim.put("audience", audience);
            claim.put("nonce", UUID.randomUUID().toString());
            claim.put("issued_at", now);
            claim.put("expires_at", now + 30);
            claim.put("method", method);
            claim.put("path", path);
            claim.put("body_digest", "sha256:" + HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(body)));
            claim.put("actor_id", actor);
            claim.put("scope", Map.copyOf(scope));
            claim.put("permissions", permissions.stream().sorted().toList());
            byte[] raw = json.writeValueAsBytes(claim);
            Signature signer = Signature.getInstance("Ed25519");
            signer.initSign(key);
            signer.update("elmos-deployment-host-v1\0".getBytes(java.nio.charset.StandardCharsets.UTF_8));
            signer.update(raw);
            var encoder = Base64.getUrlEncoder().withoutPadding();
            return keyId + "." + encoder.encodeToString(raw) + "." + encoder.encodeToString(signer.sign());
        } catch (java.security.GeneralSecurityException | java.io.IOException error) {
            throw new IllegalStateException("DEPLOYMENT_SIGNING_UNAVAILABLE", error);
        }
    }
}
