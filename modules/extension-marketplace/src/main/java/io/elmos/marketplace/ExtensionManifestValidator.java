package io.elmos.marketplace;

import java.util.Set;
import static io.elmos.marketplace.MarketplaceModels.*;

public final class ExtensionManifestValidator {
    private static final Set<String> ALLOWED_PERMISSIONS=Set.of(
            "repository:read","artifact:read","artifact:write","evidence:write",
            "runner:submit","model:invoke","network:declared","secret:lease");

    public PolicyDecision validate(ExtensionManifest manifest) {
        if (blank(manifest.extensionId()) || !manifest.extensionId().matches("[a-z0-9]+(?:[.-][a-z0-9]+)+")) return PolicyDecision.deny("EXTENSION_ID_INVALID");
        if (blank(manifest.publisherId()) || blank(manifest.tenantId())) return PolicyDecision.deny("PUBLISHER_AND_TENANT_REQUIRED");
        if (!semver(manifest.version()) || !semver(manifest.productVersion())) return PolicyDecision.deny("EXACT_VERSION_REQUIRED");
        if (!Digests.exact(manifest.releaseDigest())) return PolicyDecision.deny("EXACT_RELEASE_DIGEST_REQUIRED");
        if (manifest.permissions().contains("*") || !ALLOWED_PERMISSIONS.containsAll(manifest.permissions())) return PolicyDecision.deny("UNDECLARED_OR_UNKNOWN_PERMISSION");
        if (manifest.entrypoints().isEmpty() || manifest.entrypoints().stream().anyMatch(value->value.isBlank() || value.contains(".."))) return PolicyDecision.deny("TYPED_ENTRYPOINT_REQUIRED");
        return PolicyDecision.allow("MANIFEST_VALID",manifest.releaseDigest());
    }
    private static boolean semver(String value) { return value!=null && value.matches("(?:0|[1-9]\\d*)\\.(?:0|[1-9]\\d*)\\.(?:0|[1-9]\\d*)(?:[-+][0-9A-Za-z.-]+)?"); }
    private static boolean blank(String value) { return value==null || value.isBlank(); }
}
