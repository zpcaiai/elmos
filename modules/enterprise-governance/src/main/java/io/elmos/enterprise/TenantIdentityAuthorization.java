package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.*;

import java.time.Duration;
import java.time.Instant;
import java.util.*;

public final class TenantIdentityAuthorization {
    private static final Map<String, Set<String>> ROLE_PERMISSIONS = Map.ofEntries(
            Map.entry("ORGANIZATION_OWNER", Set.of("organization:manage", "billing:read", "billing:manage", "member:manage", "evidence:read")),
            Map.entry("PLATFORM_ADMIN", Set.of("platform:configure", "runner:manage", "integration:manage")),
            Map.entry("MIGRATION_ADMIN", Set.of("repository:read", "migration:plan", "migration:execute", "recipe:approve")),
            Map.entry("DEVELOPER", Set.of("repository:read", "assessment:run", "migration:request", "patch:read")),
            Map.entry("REVIEWER", Set.of("migration:review", "patch:review", "technical:decide")),
            Map.entry("SECURITY_REVIEWER", Set.of("security:review", "risk:accept", "model:govern", "secret:govern")),
            Map.entry("DATABASE_REVIEWER", Set.of("database:review", "rollback:approve")),
            Map.entry("AUDITOR", Set.of("audit:read", "audit:export", "evidence:read")),
            Map.entry("BILLING_ADMIN", Set.of("billing:read", "billing:manage", "quota:manage")),
            Map.entry("RUNNER_ADMIN", Set.of("runner:manage", "runner:drain", "runner:upgrade"))
    );

    public TenantContext deriveTenantContext(VerifiedPrincipal principal, Organization organization,
                                             String requestedOrganizationId, String correlationId) {
        EnterpriseModels.require(requestedOrganizationId, "requestedOrganizationId");
        if (!organization.organizationId().equals(requestedOrganizationId)) {
            throw new SecurityException("ORGANIZATION_SELECTION_MISMATCH");
        }
        Set<String> roles = principal.organizationRoles().get(requestedOrganizationId);
        if (roles == null || roles.isEmpty()) throw new SecurityException("MEMBERSHIP_REQUIRED");
        if (organization.status() != OrganizationStatus.ACTIVE) throw new SecurityException("ORGANIZATION_NOT_ACTIVE");
        return new TenantContext(organization.organizationId(), principal.actorId(), roles, principal.assurance(),
                organization.dataRegion(), correlationId);
    }

    public List<String> transactionLocalSettings(TenantContext context) {
        return List.of("SET LOCAL app.organization_id = '" + sqlLiteral(context.organizationId()) + "'",
                "SET LOCAL app.actor_id = '" + sqlLiteral(context.actorId()) + "'");
    }

    public String cacheKey(TenantContext context, String resourceType, String resourceId) {
        return "elmos:" + context.organizationId() + ":" + normalize(resourceType) + ":" + resourceId;
    }

    public String objectStoragePrefix(TenantContext context, String category) {
        if (!Set.of("snapshots", "evidence", "reports", "artifacts").contains(category)) {
            throw new IllegalArgumentException("UNSUPPORTED_STORAGE_CATEGORY");
        }
        return "organizations/" + context.organizationId() + "/" + category + "/";
    }

    public void verifyResourceBoundary(TenantContext context, String resourceOrganizationId) {
        if (!context.organizationId().equals(resourceOrganizationId)) throw new SecurityException("CROSS_TENANT_ACCESS_DENIED");
    }

    public FederatedIdentity validateFederatedIdentity(IdentityAssertion assertion,
                                                       Map<String, Set<String>> allowedGroupMappings,
                                                       Instant now) {
        EnterpriseModels.require(assertion.connectionId(), "connectionId");
        EnterpriseModels.require(assertion.subject(), "subject");
        if (!Objects.equals(assertion.issuer(), assertion.expectedIssuer())) throw new SecurityException("ISSUER_MISMATCH");
        if (!Objects.equals(assertion.audience(), assertion.expectedAudience())) throw new SecurityException("AUDIENCE_MISMATCH");
        if (!assertion.signed()) throw new SecurityException("UNSIGNED_ASSERTION");
        if (assertion.expiresAt() == null || !now.isBefore(assertion.expiresAt())) throw new SecurityException("ASSERTION_EXPIRED");
        if (assertion.protocol() == AuthenticationProtocol.OIDC && (!assertion.nonceFresh() || assertion.nonce() == null)) {
            throw new SecurityException("NONCE_REPLAY_OR_MISSING");
        }
        if (!assertion.domainVerified()) throw new SecurityException("DOMAIN_NOT_VERIFIED");
        Set<String> roles = new TreeSet<>();
        assertion.externalGroups().forEach(group -> roles.addAll(allowedGroupMappings.getOrDefault(group, Set.of())));
        if (roles.isEmpty()) throw new SecurityException("NO_MAPPED_ORGANIZATION_ROLE");
        String stableId = UUID.nameUUIDFromBytes((assertion.connectionId() + "\u0000" + assertion.subject())
                .getBytes(java.nio.charset.StandardCharsets.UTF_8)).toString();
        return new FederatedIdentity(stableId, assertion.connectionId(), assertion.subject(), assertion.email(), roles);
    }

    public AuthorizationDecision authorize(AuthorizationRequest request, Instant now) {
        TenantContext tenant = request.tenant();
        List<String> reasons = new ArrayList<>();
        if (!tenant.organizationId().equals(request.resourceOrganizationId())) reasons.add("CROSS_TENANT_ACCESS_DENIED");
        boolean permitted = tenant.roles().stream().map(role -> ROLE_PERMISSIONS.getOrDefault(role, Set.of()))
                .anyMatch(permissions -> permissions.contains(request.action()));
        if (!permitted) reasons.add("NO_EXPLICIT_PERMISSION");
        boolean highRisk = Set.of("HIGH", "CRITICAL").contains(request.attributes().get("risk"));
        if (highRisk && assuranceRank(tenant.assurance()) < assuranceRank(AuthenticationAssurance.MFA)) {
            return decision(AuthorizationResult.REQUIRE_STEP_UP, List.of("HIGH_RISK_REQUIRES_MFA"), request);
        }
        boolean sameAuthor = request.planAuthorId() != null && request.planAuthorId().equals(tenant.actorId());
        boolean alreadyApproved = request.priorApproverIds().contains(tenant.actorId());
        if (highRisk && (sameAuthor || alreadyApproved) && Set.of("migration:review", "risk:accept", "delivery:accept").contains(request.action())) {
            return decision(AuthorizationResult.REQUIRE_APPROVAL, List.of("SEPARATION_OF_DUTIES_REQUIRED"), request);
        }
        String privilegeExpiry = request.attributes().get("temporaryPrivilegeExpiresAt");
        if (privilegeExpiry != null && !now.isBefore(Instant.parse(privilegeExpiry))) reasons.add("TEMPORARY_PRIVILEGE_EXPIRED");
        if (!reasons.isEmpty()) return decision(AuthorizationResult.DENY, reasons, request);
        if (highRisk) return decision(AuthorizationResult.REQUIRE_APPROVAL, List.of("SECOND_APPROVER_REQUIRED"), request);
        return decision(AuthorizationResult.ALLOW, List.of("EXPLICIT_POLICY_ALLOW"), request);
    }

    public boolean recentAuthentication(VerifiedPrincipal principal, Instant now, Duration maximumAge) {
        return !principal.authenticatedAt().isAfter(now) && principal.authenticatedAt().plus(maximumAge).isAfter(now);
    }

    public Organization transition(Organization organization, OrganizationStatus target) {
        Map<OrganizationStatus, Set<OrganizationStatus>> allowed = Map.of(
                OrganizationStatus.PROVISIONING, Set.of(OrganizationStatus.ACTIVE, OrganizationStatus.SECURITY_RESTRICTED),
                OrganizationStatus.ACTIVE, Set.of(OrganizationStatus.SUSPENDED, OrganizationStatus.BILLING_RESTRICTED,
                        OrganizationStatus.SECURITY_RESTRICTED, OrganizationStatus.DELETION_REQUESTED, OrganizationStatus.RETENTION_HOLD),
                OrganizationStatus.SUSPENDED, Set.of(OrganizationStatus.ACTIVE, OrganizationStatus.DELETION_REQUESTED),
                OrganizationStatus.BILLING_RESTRICTED, Set.of(OrganizationStatus.ACTIVE, OrganizationStatus.DELETION_REQUESTED),
                OrganizationStatus.SECURITY_RESTRICTED, Set.of(OrganizationStatus.ACTIVE, OrganizationStatus.DELETION_REQUESTED),
                OrganizationStatus.DELETION_REQUESTED, Set.of(OrganizationStatus.DELETING, OrganizationStatus.RETENTION_HOLD),
                OrganizationStatus.RETENTION_HOLD, Set.of(OrganizationStatus.ACTIVE, OrganizationStatus.DELETION_REQUESTED),
                OrganizationStatus.DELETING, Set.of(OrganizationStatus.DELETED)
        );
        if (!allowed.getOrDefault(organization.status(), Set.of()).contains(target)) {
            throw new IllegalStateException("ILLEGAL_ORGANIZATION_TRANSITION");
        }
        return new Organization(organization.organizationId(), organization.displayName(), target,
                organization.isolationClass(), organization.dataRegion(), organization.encryptionContextId());
    }

    private static AuthorizationDecision decision(AuthorizationResult result, List<String> reasons, AuthorizationRequest request) {
        return new AuthorizationDecision(result, reasons, request.tenant().actorId(), request.tenant().organizationId(),
                request.resourceId(), request.action(), request.policyVersion());
    }
    private static int assuranceRank(AuthenticationAssurance assurance) {
        return switch (assurance) {
            case UNKNOWN -> 0; case PASSWORD -> 1; case MFA -> 2; case PHISHING_RESISTANT -> 3;
            case HARDWARE_BOUND -> 4; case SERVICE_IDENTITY -> 2;
        };
    }
    private static String normalize(String value) { return value.toLowerCase(Locale.ROOT).replace('_', '-'); }
    private static String sqlLiteral(String value) { return value.replace("'", "''"); }
}
