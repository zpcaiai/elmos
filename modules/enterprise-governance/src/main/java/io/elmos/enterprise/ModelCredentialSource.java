package io.elmos.enterprise;

import java.util.Optional;

/**
 * Where a real API credential for a catalog model would come from. Kept as an
 * interface so provisioning logic never hard-codes a single secret backend;
 * production deployments would supply a Vault/KMS-backed implementation
 * through the same {@code SecretLease} machinery used elsewhere in this
 * module, not a new bespoke path.
 */
public interface ModelCredentialSource {
    /**
     * @return the credential for {@code modelId}, or empty if none is
     * configured. Never throws for "not configured" — that is a normal,
     * expected, fail-closed outcome, not an error.
     */
    Optional<String> credentialFor(String modelId);
}
