package io.elmos.marketplace;

import java.math.BigDecimal;
import java.security.PublicKey;
import java.util.List;
import java.util.Set;

public final class MarketplaceModels {
    private MarketplaceModels() {}

    public enum Decision { ALLOW, DENY, ESCALATE }
    public enum ReleaseStatus { DRAFT, SUBMITTED, CERTIFIED, PUBLISHED, QUARANTINED, REVOKED, WITHDRAWN }

    public record PolicyDecision(Decision decision, String code, List<String> evidence) {
        public PolicyDecision { evidence=List.copyOf(evidence); }
        public static PolicyDecision allow(String code,String evidence) { return new PolicyDecision(Decision.ALLOW,code,List.of(evidence)); }
        public static PolicyDecision deny(String code) { return new PolicyDecision(Decision.DENY,code,List.of()); }
        public static PolicyDecision escalate(String code,String evidence) { return new PolicyDecision(Decision.ESCALATE,code,List.of(evidence)); }
    }

    public record ExtensionManifest(String extensionId,String publisherId,String version,String productVersion,
                                    String releaseDigest,String tenantId,Set<String> permissions,
                                    Set<String> entrypoints) {
        public ExtensionManifest { permissions=Set.copyOf(permissions); entrypoints=Set.copyOf(entrypoints); }
    }
    public record SandboxPolicy(String defaultAction,Set<String> networkAllowlist,Set<String> filesystemPaths,
                                Set<String> allowedProcesses,Set<String> secretRefs,boolean privileged,
                                boolean persistentCredentials) {
        public SandboxPolicy { networkAllowlist=Set.copyOf(networkAllowlist); filesystemPaths=Set.copyOf(filesystemPaths); allowedProcesses=Set.copyOf(allowedProcesses); secretRefs=Set.copyOf(secretRefs); }
    }
    public record CompatibilityContract(String productVersion,String protocolVersion,String sdkVersion,
                                        Set<String> supportedProductVersions,boolean publicApi,
                                        long deprecationExitEpochSecond) {
        public CompatibilityContract { supportedProductVersions=Set.copyOf(supportedProductVersions); }
    }
    public record PublisherProfile(String publisherId,boolean verified,boolean active,boolean mfa,
                                   boolean separationOfDuties,Set<String> identityEvidence,
                                   Set<String> activeSigningKeys,String securityContact) {
        public PublisherProfile { identityEvidence=Set.copyOf(identityEvidence); activeSigningKeys=Set.copyOf(activeSigningKeys); }
    }
    public record ReleaseRecord(String releaseId,String extensionId,String publisherId,ReleaseStatus status,
                                String digest,boolean immutable,String sbomDigest,String provenanceDigest) {}
    public record SupplyChainEnvelope(byte[] artifact,byte[] signature,PublicKey publicKey,String expectedDigest,
                                      String sbomDigest,String provenanceDigest) {
        public SupplyChainEnvelope { artifact=artifact.clone(); signature=signature.clone(); }
        @Override public byte[] artifact() { return artifact.clone(); }
        @Override public byte[] signature() { return signature.clone(); }
    }
    public record Dependency(String extensionId,String version,String digest,Set<String> dependsOn,boolean revoked) {
        public Dependency { dependsOn=Set.copyOf(dependsOn); }
    }
    public record InstallationRequest(String idempotencyKey,String tenantId,String extensionId,String releaseDigest,
                                      Set<String> grantedPermissions,boolean compatible,boolean revoked) {
        public InstallationRequest { grantedPermissions=Set.copyOf(grantedPermissions); }
    }
    public record Installation(String installationId,String tenantId,String extensionId,String releaseDigest,
                               Set<String> grantedPermissions,boolean active) {
        public Installation { grantedPermissions=Set.copyOf(grantedPermissions); }
    }
    public record RuntimeHealth(String expectedDigest,String observedDigest,int openCriticalIncidents,
                                int leakedCredentials,int orphanProcesses,boolean quarantined) {}
    public record OfflineMirror(String bundleDigest,String expectedDigest,String trustRoot,Set<String> trustedRoots,
                                Set<String> requestedPermissions,Set<String> onlineGrantedPermissions,
                                long revocationAgeSeconds,long maximumRevocationAgeSeconds,boolean signed,
                                boolean networkEnabled) {
        public OfflineMirror { trustedRoots=Set.copyOf(trustedRoots); requestedPermissions=Set.copyOf(requestedPermissions); onlineGrantedPermissions=Set.copyOf(onlineGrantedPermissions); }
    }
    public record Settlement(BigDecimal gross,BigDecimal refunds,BigDecimal taxes,BigDecimal publisherShare,
                             BigDecimal platformShare,BigDecimal hold,BigDecimal providerBilled,
                             boolean openFraudFinding) {}
    public record EolPlan(Set<String> installedTenants,Set<String> notifiedTenants,Set<String> exportedTenants,
                          Set<String> uninstalledTenants,Set<String> residualDependencies,boolean replacementAvailable) {
        public EolPlan { installedTenants=Set.copyOf(installedTenants); notifiedTenants=Set.copyOf(notifiedTenants); exportedTenants=Set.copyOf(exportedTenants); uninstalledTenants=Set.copyOf(uninstalledTenants); residualDependencies=Set.copyOf(residualDependencies); }
    }
}
