package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class DeploymentHostSignerTest {
    @Test
    void signatureBindsExactEnvelopeAndChangesNonceOnRetry() throws Exception {
        var pair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        var json = new ObjectMapper();
        var signer = new DeploymentHostSigner("host", "worker", pair.getPrivate(),
                Clock.fixed(Instant.ofEpochSecond(100), ZoneOffset.UTC), json);
        var scope = Map.of("tenant_id", "tenant", "workspace_id", "workspace", "project_id", "project",
                           "environment_id", "test", "account_id", "account");
        byte[] body = "{}".getBytes(StandardCharsets.UTF_8);
        String token = signer.sign("POST", "/v1/deployments", body, "actor", scope, Set.of("deployment:apply"));
        String[] parts = token.split("\\.");
        byte[] raw = Base64.getUrlDecoder().decode(parts[1]);
        var verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update("elmos-deployment-host-v1\0".getBytes(StandardCharsets.UTF_8));
        verifier.update(raw);
        assertTrue(verifier.verify(Base64.getUrlDecoder().decode(parts[2])));
        var claim = json.readTree(raw);
        assertEquals(130, claim.get("expires_at").asLong());
        assertEquals("tenant", claim.get("scope").get("tenant_id").asText());
        assertEquals("/v1/deployments", claim.get("path").asText());
        assertNotEquals(token, signer.sign("POST", "/v1/deployments", body, "actor", scope, Set.of("deployment:apply")));
        raw[raw.length - 2] ^= 1;
        verifier.initVerify(pair.getPublic());
        verifier.update("elmos-deployment-host-v1\0".getBytes(StandardCharsets.UTF_8));
        verifier.update(raw);
        assertFalse(verifier.verify(Base64.getUrlDecoder().decode(parts[2])));
    }

    @Test
    void rejectsIncompleteResourceBinding() {
        assertThrows(IllegalArgumentException.class, () -> new ReleaseDeploymentController.Binding(
                Map.of("tenant_id", "tenant"), Map.of("actor", Set.of("deployment:apply"))));
    }
}
