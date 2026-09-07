package io.elmos.enterprise;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class EnterpriseModels {
    private EnterpriseModels() {}

    public enum OrganizationStatus { PROVISIONING, ACTIVE, SUSPENDED, BILLING_RESTRICTED,
        SECURITY_RESTRICTED, DELETION_REQUESTED, RETENTION_HOLD, DELETING, DELETED }
    public enum IsolationClass { T1_SHARED_SAAS, T2_DEDICATED_DATA_PLANE, T3_DEDICATED_DEPLOYMENT, T4_AIR_GAPPED }
    public enum AuthenticationProtocol { OIDC, SAML }
    public enum AuthenticationAssurance { PASSWORD, MFA, PHISHING_RESISTANT, HARDWARE_BOUND, SERVICE_IDENTITY, UNKNOWN }
    public enum AuthorizationResult { ALLOW, DENY, ALLOW_WITH_CONDITIONS, REQUIRE_APPROVAL, REQUIRE_STEP_UP }
    public enum RunnerStatus { ENROLLING, ACTIVE, DRAINING, OFFLINE, UNHEALTHY, QUARANTINED, REVOKED, DECOMMISSIONED }
    public enum SourceUploadPolicy { NO_SOURCE_UPLOAD, PATCH_ONLY, METADATA_ONLY, SELECTED_SNIPPETS, FULL_EVIDENCE }
    public enum SecretPurpose { SCM_READ, SCM_WRITE_BRANCH, MAVEN_READ, ARTIFACT_WRITE, SONAR_READ, SONAR_ANALYZE,
        MODEL_INVOKE, DATABASE_TEST, CONTAINER_REGISTRY_READ, SIGNING_KEY, ENCRYPTION_KEY, BACKUP_KEY }
    public enum DataClassification { PUBLIC_CODE, OPEN_SOURCE, INTERNAL_CODE, CONFIDENTIAL_CODE, RESTRICTED_CODE,
        SECRET, PERSONAL_DATA }
    public enum ModelProviderType { ELMOS_MANAGED, CUSTOMER_BYOK, CUSTOMER_PRIVATE_ENDPOINT,
        ON_PREMISES_MODEL, OPENHANDS_LOCAL, OFFLINE_MODEL }
    public enum ModelDecisionStatus { ALLOW, BLOCKED, HUMAN_REQUIRED }
    public enum ReservationStatus { RESERVED, COMMITTED, RELEASED, REJECTED }
    public enum DeletionStatus { REQUESTED, VALIDATING, BLOCKED_BY_LEGAL_HOLD, SCHEDULED,
        DELETING_PRIMARY, DELETING_REPLICAS, BACKUP_EXPIRATION_PENDING, CRYPTO_SHREDDED,
        COMPLETED, COMPLETED_WITH_LIMITATIONS, FAILED }
    public enum DeploymentMode { SHARED_SAAS, DEDICATED_SAAS, HYBRID_PRIVATE_RUNNER,
        PRIVATE_VPC, ON_PREMISES_CONNECTED, ON_PREMISES_RESTRICTED_EGRESS, AIR_GAPPED }
    public enum CapabilityStatus { AVAILABLE, NOT_CONFIGURED, BLOCKED }

    public record Organization(String organizationId, String displayName, OrganizationStatus status,
                               IsolationClass isolationClass, String dataRegion, String encryptionContextId) {
        public Organization {
            require(organizationId, "organizationId"); require(displayName, "displayName");
            require(dataRegion, "dataRegion"); require(encryptionContextId, "encryptionContextId");
        }
    }

    public record VerifiedPrincipal(String actorId, Map<String, Set<String>> organizationRoles,
                                    AuthenticationAssurance assurance, Instant authenticatedAt,
                                    boolean serviceIdentity) {
        public VerifiedPrincipal {
            require(actorId, "actorId"); organizationRoles = immutableNestedSetMap(organizationRoles);
            if (assurance == null || authenticatedAt == null) throw new IllegalArgumentException("verified principal is incomplete");
        }
    }

    public record TenantContext(String organizationId, String actorId, Set<String> roles,
                                AuthenticationAssurance assurance, String dataRegion, String correlationId) {
        public TenantContext {
            require(organizationId, "organizationId"); require(actorId, "actorId"); require(dataRegion, "dataRegion");
            require(correlationId, "correlationId"); roles = Set.copyOf(roles);
        }
    }

    public record IdentityAssertion(AuthenticationProtocol protocol, String connectionId, String issuer,
                                    String expectedIssuer, String audience, String expectedAudience,
                                    String subject, String email, String nonce, boolean nonceFresh,
                                    boolean signed, Instant expiresAt, boolean domainVerified,
                                    Set<String> externalGroups) {
        public IdentityAssertion { externalGroups = Set.copyOf(externalGroups); }
    }

    public record FederatedIdentity(String identityId, String connectionId, String providerSubject,
                                    String currentEmail, Set<String> mappedRoles) {
        public FederatedIdentity { mappedRoles = Set.copyOf(mappedRoles); }
    }

    public record AuthorizationRequest(TenantContext tenant, String resourceOrganizationId,
                                       String resourceType, String resourceId, String action,
                                       Map<String, String> attributes, String planAuthorId,
                                       Set<String> priorApproverIds, String policyVersion) {
        public AuthorizationRequest {
            require(resourceOrganizationId, "resourceOrganizationId"); require(resourceType, "resourceType");
            require(resourceId, "resourceId"); require(action, "action"); require(policyVersion, "policyVersion");
            attributes = Map.copyOf(attributes); priorApproverIds = Set.copyOf(priorApproverIds);
        }
    }

    public record AuthorizationDecision(AuthorizationResult decision, List<String> reasonCodes,
                                        String actorId, String organizationId, String resourceId,
                                        String action, String policyVersion) {
        public AuthorizationDecision { reasonCodes = List.copyOf(reasonCodes); }
    }

    public record RunnerNode(String runnerId, String organizationId, String poolId, RunnerStatus status,
                             Set<String> capabilities, String capabilityHash, String certificateThumbprint,
                             Instant certificateExpiresAt, SourceUploadPolicy uploadPolicy) {
        public RunnerNode { capabilities = Set.copyOf(capabilities); }
    }

    public record RunnerJob(String jobId, String organizationId, Set<String> requiredCapabilities,
                            String inputManifestHash, String idempotencyKey, int attempt) {
        public RunnerJob { requiredCapabilities = Set.copyOf(requiredCapabilities); }
    }

    public record RunnerJobLease(String leaseId, String jobId, String runnerId, String organizationId,
                                 int attempt, Instant issuedAt, Instant expiresAt, String jobTokenHash) {}

    public record SecretReference(String referenceId, String organizationId, SecretPurpose purpose,
                                  String provider, String path, boolean developmentProvider) {}
    public record WorkloadIdentity(String organizationId, String runnerId, String jobId, String migrationStepId) {}
    public record SecretLease(String leaseId, String referenceId, WorkloadIdentity workload,
                              SecretPurpose purpose, Instant issuedAt, Instant expiresAt, boolean renewable,
                              boolean revoked) {}

    public record ModelPolicy(String policyVersion, Set<ModelProviderType> allowedProviders,
                              Set<String> allowedRegions, Set<DataClassification> allowedClassifications,
                              boolean sourceCodeMayLeavePrivateNetwork, int maximumSnippetCharacters,
                              boolean retainPrompt, boolean retainResponse) {
        public ModelPolicy {
            allowedProviders = Set.copyOf(allowedProviders); allowedRegions = Set.copyOf(allowedRegions);
            allowedClassifications = Set.copyOf(allowedClassifications);
        }
    }

    public record ModelEndpoint(String providerId, ModelProviderType type, String organizationId,
                                String region, String modelVersion, boolean approved, boolean healthy,
                                Set<String> profiles) {
        public ModelEndpoint { profiles = Set.copyOf(profiles); }
    }

    public record ModelRequest(String invocationId, String organizationId, String modelProfile,
                               DataClassification classification, int snippetCharacters, boolean secretScanPassed,
                               BigDecimal maximumCost, String contextPackHash, String toolPolicyHash) {
        public ModelRequest {
            require(invocationId, "invocationId"); require(organizationId, "organizationId");
            require(modelProfile, "modelProfile"); require(contextPackHash, "contextPackHash");
            require(toolPolicyHash, "toolPolicyHash");
            if (classification == null || snippetCharacters < 0 || maximumCost == null || maximumCost.signum() < 0)
                throw new IllegalArgumentException("model request budget and classification are invalid");
        }
    }

    public record ModelRoutingDecision(ModelDecisionStatus status, String providerId, String modelVersion,
                                       List<String> reasonCodes, String policyVersion, boolean contentRetained) {
        public ModelRoutingDecision { reasonCodes = List.copyOf(reasonCodes); }
    }

    public record UsageEvent(String eventId, String organizationId, String resourceType, BigDecimal quantity,
                             String unit, Instant occurredAt, String sourceId, String idempotencyKey,
                             String costSnapshotId) {}
    public record UsageReservation(String reservationId, String organizationId, BigDecimal amount,
                                   ReservationStatus status, String idempotencyKey, Instant expiresAt) {}
    public record LedgerEntry(String entryId, String organizationId, BigDecimal amount,
                              String entryType, String sourceId, String reversesEntryId, Instant occurredAt) {}

    public record AuditDraft(String eventId, String organizationId, String actorType, String actorId,
                             String action, String resourceType, String resourceId, String decision,
                             String policyVersion, String beforeHash, String afterHash,
                             String correlationId, Instant occurredAt, Map<String, String> metadata) {
        public AuditDraft { metadata = Map.copyOf(metadata); }
    }
    public record AuditEvent(AuditDraft event, String previousHash, String eventHash) {}
    public record AuditVerification(boolean valid, int verifiedEvents, List<String> reasonCodes) {
        public AuditVerification { reasonCodes = List.copyOf(reasonCodes); }
    }

    public record DataInventoryEntry(String inventoryId, String organizationId, String dataType,
                                     String region, String storageRef, DataClassification classification,
                                     String retentionPolicyId, String encryptionContextId, Instant createdAt) {}
    public record LegalHold(String holdId, String organizationId, Set<String> coveredDataTypes,
                            Instant effectiveAt, Instant expiresAt, boolean released) {
        public LegalHold { coveredDataTypes = Set.copyOf(coveredDataTypes); }
    }
    public record DeletionDecision(DeletionStatus status, List<String> reasonCodes,
                                   List<String> requiredTargets, boolean cryptoShredAllowed) {
        public DeletionDecision { reasonCodes = List.copyOf(reasonCodes); requiredTargets = List.copyOf(requiredTargets); }
    }

    public record ReleaseBundle(String bundleId, String version, Map<String, String> artifactDigests,
                                boolean signatureValid, boolean sbomPresent, boolean malwareScanPassed,
                                boolean requiresPublicNetwork) {
        public ReleaseBundle { artifactDigests = Map.copyOf(artifactDigests); }
    }
    public record OfflineLicense(String installationId, String edition, Set<String> features,
                                 int maximumRunners, Instant validFrom, Instant validUntil,
                                 int gracePeriodDays, boolean signatureValid) {
        public OfflineLicense { features = Set.copyOf(features); }
    }
    public record DeploymentDecision(CapabilityStatus status, List<String> reasonCodes,
                                     boolean historicalEvidenceReadable, boolean newWorkAllowed) {
        public DeploymentDecision { reasonCodes = List.copyOf(reasonCodes); }
    }

    static void require(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
    }
    private static Map<String, Set<String>> immutableNestedSetMap(Map<String, Set<String>> input) {
        return input.entrySet().stream().collect(java.util.stream.Collectors.toUnmodifiableMap(
                Map.Entry::getKey, entry -> Set.copyOf(entry.getValue())));
    }
}
