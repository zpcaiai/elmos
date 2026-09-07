package io.elmos.marketplace;

import java.util.LinkedHashMap;
import java.util.Map;
import static io.elmos.marketplace.MarketplaceModels.*;

public final class InstallationRegistry {
    private final Map<String,Installation> byRequest=new LinkedHashMap<>();
    public synchronized PolicyDecision install(InstallationRequest request,ExtensionManifest manifest) {
        if (blank(request.idempotencyKey()) || blank(request.tenantId())) return PolicyDecision.deny("INSTALLATION_SCOPE_REQUIRED");
        if (!request.tenantId().equals(manifest.tenantId())) return PolicyDecision.deny("CROSS_TENANT_INSTALL_DENIED");
        if (!request.extensionId().equals(manifest.extensionId()) || !request.releaseDigest().equals(manifest.releaseDigest())) return PolicyDecision.deny("INSTALLATION_RELEASE_MISMATCH");
        if (!request.compatible() || request.revoked()) return PolicyDecision.deny("INCOMPATIBLE_OR_REVOKED_INSTALL_DENIED");
        if (!manifest.permissions().containsAll(request.grantedPermissions())) return PolicyDecision.deny("PERMISSION_ESCALATION_DENIED");
        Installation existing=byRequest.get(request.idempotencyKey());
        if (existing!=null) {
            if (!existing.tenantId().equals(request.tenantId()) || !existing.releaseDigest().equals(request.releaseDigest())) return PolicyDecision.deny("IDEMPOTENCY_KEY_CONFLICT");
            return PolicyDecision.allow("INSTALLATION_REPLAYED",existing.installationId());
        }
        String id="installation-"+(byRequest.size()+1); byRequest.put(request.idempotencyKey(),new Installation(id,request.tenantId(),request.extensionId(),request.releaseDigest(),request.grantedPermissions(),true));
        return PolicyDecision.allow("INSTALLATION_CREATED",id);
    }
    public synchronized PolicyDecision revoke(String idempotencyKey,String tenantId) {
        Installation current=byRequest.get(idempotencyKey);
        if (current==null || !current.tenantId().equals(tenantId)) return PolicyDecision.deny("INSTALLATION_NOT_FOUND_IN_TENANT");
        byRequest.put(idempotencyKey,new Installation(current.installationId(),current.tenantId(),current.extensionId(),current.releaseDigest(),current.grantedPermissions(),false));
        return PolicyDecision.allow("INSTALLATION_REVOKED",current.installationId());
    }
    private static boolean blank(String value) { return value==null || value.isBlank(); }
}
