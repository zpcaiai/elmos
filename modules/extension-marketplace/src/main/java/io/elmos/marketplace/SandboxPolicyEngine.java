package io.elmos.marketplace;

import java.nio.file.Path;
import static io.elmos.marketplace.MarketplaceModels.*;

public final class SandboxPolicyEngine {
    public PolicyDecision validate(SandboxPolicy policy) {
        if (!"deny".equals(policy.defaultAction())) return PolicyDecision.deny("SANDBOX_DEFAULT_DENY_REQUIRED");
        if (policy.privileged()) return PolicyDecision.deny("PRIVILEGED_EXECUTION_DENIED");
        if (policy.persistentCredentials()) return PolicyDecision.deny("PERSISTENT_CREDENTIALS_DENIED");
        if (policy.networkAllowlist().stream().anyMatch(value->value.equals("*") || value.equals("0.0.0.0/0") || value.equals("::/0"))) return PolicyDecision.deny("WILDCARD_NETWORK_DENIED");
        if (policy.filesystemPaths().stream().anyMatch(SandboxPolicyEngine::hostPath)) return PolicyDecision.deny("HOST_PATH_DENIED");
        if (policy.allowedProcesses().stream().anyMatch(value->value.equals("*") || value.contains("shell"))) return PolicyDecision.deny("UNTYPED_PROCESS_DENIED");
        if (policy.secretRefs().stream().anyMatch(value->!value.matches("lease:[a-z0-9-]+"))) return PolicyDecision.deny("SCOPED_SECRET_LEASE_REQUIRED");
        return PolicyDecision.allow("SANDBOX_POLICY_VALID","default-deny");
    }
    public PolicyDecision authorize(ExtensionManifest manifest,SandboxPolicy policy,String tenantId,String permission) {
        PolicyDecision valid=validate(policy); if (valid.decision()!=Decision.ALLOW) return valid;
        if (!manifest.tenantId().equals(tenantId)) return PolicyDecision.deny("CROSS_TENANT_EXECUTION_DENIED");
        if (!manifest.permissions().contains(permission)) return PolicyDecision.deny("PERMISSION_NOT_DECLARED");
        return PolicyDecision.allow("SANDBOX_ACTION_AUTHORIZED",manifest.releaseDigest());
    }
    private static boolean hostPath(String value) {
        if (value==null || value.isBlank()) return true;
        try { return Path.of(value).isAbsolute() || value.contains(".."); } catch (RuntimeException ignored) { return true; }
    }
}
