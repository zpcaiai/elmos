package io.elmos.enterprise;

import java.util.Optional;

/**
 * Default {@link ModelCredentialSource}: looks for an environment variable
 * named {@code ELMOS_MODEL_CREDENTIAL_<MODEL_ID>} (model id upper-cased,
 * {@code .} and {@code -} folded to {@code _}). No such variable is set for
 * any catalog model today, so every lookup returns empty and provisioning
 * stays {@code NOT_CONFIGURED} until an operator supplies a real credential
 * through the environment (or a stronger implementation, e.g. a Vault-backed
 * one, replaces this class at wiring time).
 */
public final class EnvModelCredentialSource implements ModelCredentialSource {
    static final String PREFIX = "ELMOS_MODEL_CREDENTIAL_";

    @Override
    public Optional<String> credentialFor(String modelId) {
        EnterpriseModels.require(modelId, "modelId");
        String value = System.getenv(environmentVariableName(modelId));
        return (value == null || value.isBlank()) ? Optional.empty() : Optional.of(value);
    }

    static String environmentVariableName(String modelId) {
        return PREFIX + modelId.toUpperCase(java.util.Locale.ROOT).replace('-', '_').replace('.', '_');
    }
}
