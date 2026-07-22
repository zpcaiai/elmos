package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.*;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class DataAndDeploymentGovernance {

    public DataInventoryEntry registerData(String inventoryId, TenantContext tenant, String dataType,
                                           String requestedRegion, Set<String> allowedRegions,
                                           String storageRef, DataClassification classification,
                                           String retentionPolicyId, String encryptionContextId, Instant now) {
        if (!allowedRegions.contains(requestedRegion) || !tenant.dataRegion().equals(requestedRegion)) {
            throw new SecurityException("DATA_RESIDENCY_VIOLATION");
        }
        EnterpriseModels.require(retentionPolicyId, "retentionPolicyId");
        EnterpriseModels.require(encryptionContextId, "encryptionContextId");
        if (!storageRef.startsWith("organizations/" + tenant.organizationId() + "/")) {
            throw new SecurityException("STORAGE_PREFIX_TENANT_MISMATCH");
        }
        return new DataInventoryEntry(inventoryId, tenant.organizationId(), dataType, requestedRegion,
                storageRef, classification, retentionPolicyId, encryptionContextId, now);
    }

    public DeletionDecision planDeletion(String organizationId, Set<String> dataTypes,
                                         List<LegalHold> holds, boolean independentOrganizationKey,
                                         boolean backupSelectiveDeletionSupported, Instant now) {
        boolean blocked = holds.stream().filter(hold -> hold.organizationId().equals(organizationId))
                .filter(hold -> !hold.released())
                .filter(hold -> !hold.effectiveAt().isAfter(now))
                .filter(hold -> hold.expiresAt() == null || now.isBefore(hold.expiresAt()))
                .anyMatch(hold -> hold.coveredDataTypes().stream().anyMatch(dataTypes::contains));
        if (blocked) return new DeletionDecision(DeletionStatus.BLOCKED_BY_LEGAL_HOLD,
                List.of("ACTIVE_LEGAL_HOLD"), List.of(), false);
        List<String> targets = new ArrayList<>(List.of("PRIMARY", "SEARCH_INDEX", "CACHE", "OBJECT_STORAGE",
                "RUNNER_SECRETS", "MODEL_RETENTION", "DELETION_TOMBSTONE"));
        targets.add(backupSelectiveDeletionSupported ? "BACKUP_DELETE" : "BACKUP_EXPIRATION_AND_RESTORE_REPLAY");
        return new DeletionDecision(DeletionStatus.SCHEDULED, List.of("LEGAL_HOLD_CLEAR"), targets,
                independentOrganizationKey);
    }

    public Set<String> reconcileRestore(Set<String> restoredInventoryIds, Set<String> deletionTombstones) {
        java.util.HashSet<String> visible = new java.util.HashSet<>(restoredInventoryIds);
        visible.removeAll(deletionTombstones);
        return Set.copyOf(visible);
    }

    public DeploymentDecision verifyBundle(ReleaseBundle bundle, DeploymentMode mode,
                                           boolean localRegistryReady, boolean localRecipeRegistryReady,
                                           boolean localVulnerabilityDbReady, boolean localIdentityReady,
                                           boolean localSecretProviderReady) {
        List<String> reasons = new ArrayList<>();
        if (!bundle.signatureValid()) reasons.add("BUNDLE_SIGNATURE_INVALID");
        if (!bundle.sbomPresent()) reasons.add("SBOM_MISSING");
        if (!bundle.malwareScanPassed()) reasons.add("MALWARE_SCAN_NOT_PASSED");
        if (bundle.artifactDigests().isEmpty() || bundle.artifactDigests().values().stream().anyMatch(value -> !value.matches("[0-9a-f]{64}"))) {
            reasons.add("ARTIFACT_DIGEST_INVALID");
        }
        if (mode == DeploymentMode.AIR_GAPPED && bundle.requiresPublicNetwork()) reasons.add("PUBLIC_NETWORK_DEPENDENCY_FORBIDDEN");
        if (!localRegistryReady) reasons.add("LOCAL_REGISTRY_NOT_READY");
        if (!localRecipeRegistryReady) reasons.add("LOCAL_RECIPE_REGISTRY_NOT_READY");
        if (!localVulnerabilityDbReady) reasons.add("LOCAL_VULNERABILITY_DB_NOT_READY");
        if (!localIdentityReady) reasons.add("LOCAL_IDENTITY_NOT_READY");
        if (!localSecretProviderReady) reasons.add("LOCAL_SECRET_PROVIDER_NOT_READY");
        return new DeploymentDecision(reasons.isEmpty() ? CapabilityStatus.AVAILABLE : CapabilityStatus.BLOCKED,
                reasons, true, reasons.isEmpty());
    }

    public DeploymentDecision evaluateOfflineLicense(OfflineLicense license, String installationId,
                                                     Instant now, boolean startNewWork) {
        if (!license.signatureValid() || !license.installationId().equals(installationId)) {
            return new DeploymentDecision(CapabilityStatus.BLOCKED, List.of("LICENSE_INVALID"), true, false);
        }
        if (now.isBefore(license.validFrom())) {
            return new DeploymentDecision(CapabilityStatus.BLOCKED, List.of("LICENSE_NOT_YET_VALID"), true, false);
        }
        Instant graceEnd = license.validUntil().plus(license.gracePeriodDays(), ChronoUnit.DAYS);
        if (now.isAfter(graceEnd)) {
            return new DeploymentDecision(CapabilityStatus.BLOCKED, List.of("LICENSE_EXPIRED"), true, false);
        }
        if (now.isAfter(license.validUntil())) {
            return new DeploymentDecision(startNewWork ? CapabilityStatus.BLOCKED : CapabilityStatus.AVAILABLE,
                    List.of("LICENSE_GRACE"), true, !startNewWork);
        }
        return new DeploymentDecision(CapabilityStatus.AVAILABLE, List.of("LICENSE_VALID"), true, true);
    }

    public Map<String, CapabilityStatus> noAgentModeCapabilities(boolean modelAvailable) {
        return Map.of("healthCheck", CapabilityStatus.AVAILABLE,
                "openRewrite", CapabilityStatus.AVAILABLE,
                "validation", CapabilityStatus.AVAILABLE,
                "agentRepair", modelAvailable ? CapabilityStatus.AVAILABLE : CapabilityStatus.NOT_CONFIGURED);
    }
}
