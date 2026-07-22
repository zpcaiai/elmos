package io.elmos.integrations;

import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.Base64;

public final class GitHubPrivateKeyLoader {
    private GitHubPrivateKeyLoader() {}
    public static PrivateKey loadPkcs8(char[] pem) {
        if (pem == null || pem.length == 0) throw new IllegalArgumentException("GitHub App private key is required");
        String text = new String(pem);
        if (!text.contains("BEGIN PRIVATE KEY") || text.contains("BEGIN RSA PRIVATE KEY"))
            throw new IllegalArgumentException("GitHub App key must be unencrypted PKCS#8 PEM supplied by a secret provider");
        try {
            String encoded = text.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", "").replaceAll("\\s", "");
            return KeyFactory.getInstance("RSA").generatePrivate(new PKCS8EncodedKeySpec(Base64.getDecoder().decode(encoded)));
        } catch (Exception exception) { throw new IllegalArgumentException("invalid GitHub App PKCS#8 private key", exception); }
        finally { java.util.Arrays.fill(pem, '\0'); }
    }
}
