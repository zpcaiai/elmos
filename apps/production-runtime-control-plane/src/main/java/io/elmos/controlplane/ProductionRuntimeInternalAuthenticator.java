package io.elmos.controlplane;

import io.elmos.productionruntime.OwnerOnlyProviderCredentialFile;
import org.springframework.security.access.AccessDeniedException;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Objects;

/** File-backed workload-token authentication for dedicated internal runtime traffic. */
final class ProductionRuntimeInternalAuthenticator {
    private final OwnerOnlyProviderCredentialFile credential;

    ProductionRuntimeInternalAuthenticator(Path credentialFile) {
        this.credential = new OwnerOnlyProviderCredentialFile(
                Objects.requireNonNull(credentialFile, "credentialFile"));
    }

    String credential() {
        return credential.read();
    }

    void require(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            throw new AccessDeniedException("PRODUCTION_RUNTIME_WORKLOAD_AUTH_REQUIRED");
        }
        byte[] expected = credential.read().getBytes(StandardCharsets.UTF_8);
        byte[] supplied = authorization.substring("Bearer ".length())
                .getBytes(StandardCharsets.UTF_8);
        if (!MessageDigest.isEqual(expected, supplied)) {
            throw new AccessDeniedException("PRODUCTION_RUNTIME_WORKLOAD_AUTH_INVALID");
        }
    }
}
