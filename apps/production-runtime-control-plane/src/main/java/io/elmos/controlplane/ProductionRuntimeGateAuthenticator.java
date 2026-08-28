package io.elmos.controlplane;

import io.elmos.productionruntime.OwnerOnlyProviderCredentialFile;
import org.springframework.security.access.AccessDeniedException;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Objects;

/** Separate credential boundary for explicitly enabled destructive/load gates in the runtime process. */
final class ProductionRuntimeGateAuthenticator {
    private final OwnerOnlyProviderCredentialFile credential;

    ProductionRuntimeGateAuthenticator(Path credentialFile) {
        this.credential = new OwnerOnlyProviderCredentialFile(
                Objects.requireNonNull(credentialFile, "credentialFile"));
    }

    void require(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            throw new AccessDeniedException("PRODUCTION_RUNTIME_GATE_AUTH_REQUIRED");
        }
        byte[] expected = credential.read().getBytes(StandardCharsets.UTF_8);
        byte[] supplied = authorization.substring("Bearer ".length())
                .getBytes(StandardCharsets.UTF_8);
        if (!MessageDigest.isEqual(expected, supplied)) {
            throw new AccessDeniedException("PRODUCTION_RUNTIME_GATE_AUTH_INVALID");
        }
    }
}
