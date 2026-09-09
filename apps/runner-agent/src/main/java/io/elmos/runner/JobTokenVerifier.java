package io.elmos.runner;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

/**
 * Verifies dispatcher-issued Ed25519 job tokens. The agent never holds the
 * private key and therefore cannot mint a token for another tenant.
 */
public final class JobTokenVerifier {

    private static final Pattern IMAGE =
            Pattern.compile("^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$");

    private final PublicKey publicKey;
    private final String keyId;
    private final Set<String> seenJti = ConcurrentHashMap.newKeySet();

    public JobTokenVerifier(Path publicKeyPem, String keyId) {
        this.publicKey = readPublicKey(publicKeyPem);
        this.keyId = keyId;
    }

    public Map<String, Object> verify(String token, String requiredScope, String expectedTenant) {
        String[] parts = token.split("\\.");
        if (parts.length != 3) {
            throw new IllegalArgumentException("JOB_TOKEN_MALFORMED");
        }
        Map<String, Object> header = Json.parseObject(new String(b64(parts[0]), StandardCharsets.UTF_8));
        if (!"EdDSA".equals(header.get("alg"))
                || !"ELMOS-JOB".equals(header.get("typ"))
                || !keyId.equals(header.get("kid"))) {
            throw new IllegalArgumentException("JOB_TOKEN_HEADER_INVALID");
        }
        if (!ed25519(parts[0] + "." + parts[1], b64(parts[2]))) {
            throw new IllegalArgumentException("JOB_TOKEN_SIGNATURE_INVALID");
        }
        Map<String, Object> payload = Json.parseObject(new String(b64(parts[1]), StandardCharsets.UTF_8));
        if (!"elmos-job-dispatcher".equals(payload.get("iss"))
                || !"elmos-runner-agent".equals(payload.get("aud"))) {
            throw new IllegalArgumentException("JOB_TOKEN_CLAIMS_INVALID");
        }
        if (!IMAGE.matcher(String.valueOf(payload.get("image"))).matches()) {
            throw new IllegalArgumentException("JOB_TOKEN_IMAGE_NOT_DIGEST_PINNED");
        }
        Object scope = payload.get("scope");
        if (!(scope instanceof Iterable<?> items) || !contains(items, requiredScope)) {
            throw new IllegalArgumentException("JOB_TOKEN_SCOPE_DENIED");
        }
        if (expectedTenant != null && !expectedTenant.equals(payload.get("tenant"))) {
            throw new IllegalArgumentException("JOB_TOKEN_TENANT_MISMATCH");
        }
        String jti = String.valueOf(payload.get("jti"));
        if (!seenJti.add(jti)) {
            throw new IllegalArgumentException("JOB_TOKEN_REPLAYED");
        }
        return payload;
    }

    private boolean ed25519(String message, byte[] signature) {
        try {
            Signature verifier = Signature.getInstance("Ed25519");
            verifier.initVerify(publicKey);
            verifier.update(message.getBytes(StandardCharsets.UTF_8));
            return verifier.verify(signature);
        } catch (Exception error) {
            throw new IllegalArgumentException("JOB_TOKEN_SIGNATURE_INVALID", error);
        }
    }

    private static boolean contains(Iterable<?> items, String required) {
        for (Object item : items) {
            if (required.equals(item)) {
                return true;
            }
        }
        return false;
    }

    private static byte[] b64(String value) {
        return Base64.getUrlDecoder().decode(value);
    }

    private static PublicKey readPublicKey(Path pem) {
        try {
            String body = Files.readString(pem)
                    .replace("-----BEGIN PUBLIC KEY-----", "")
                    .replace("-----END PUBLIC KEY-----", "")
                    .replaceAll("\\s", "");
            byte[] decoded = Base64.getDecoder().decode(body);
            return KeyFactory.getInstance("Ed25519").generatePublic(new X509EncodedKeySpec(decoded));
        } catch (Exception error) {
            throw new IllegalStateException("JOB_TOKEN_PUBLIC_KEY_UNREADABLE", error);
        }
    }
}
