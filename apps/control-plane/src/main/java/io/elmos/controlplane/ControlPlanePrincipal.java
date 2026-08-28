package io.elmos.controlplane;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

record ControlPlanePrincipal(
        String organizationId,
        String accountId,
        String actorId,
        Set<String> roles,
        Set<String> permissions,
        Map<String, TenantGrant> memberships
) {
    record TenantGrant(Set<String> roles, Set<String> permissions) {
        TenantGrant {
            roles = Set.copyOf(roles);
            permissions = Set.copyOf(permissions);
        }
    }

    private static final Pattern ORGANIZATION =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");
    private static final Pattern ACCOUNT =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,95}");
    private static final Pattern ACTOR =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}");
    private static final Set<String> KNOWN_PERMISSIONS = Set.of(
            "workspace:view", "spring:execute", "translation:execute",
            "generation:execute", "repository:read", "repository:write",
            "repository:commit", "repository:push", "repository:pr",
            "modernization:execute",
            "usage:read", "billing:write", "admin:read", "admin:operate",
            "admin:approve", "configuration:manage");
    private static final Map<String, Set<String>> ROLE_PERMISSIONS = Map.of(
            "VIEWER", Set.of("workspace:view", "repository:read", "usage:read"),
            "DEVELOPER", Set.of(
                    "workspace:view", "spring:execute", "translation:execute",
                    "generation:execute", "repository:read", "repository:write",
                    "repository:commit", "modernization:execute", "usage:read"),
            "MAINTAINER", Set.of(
                    "workspace:view", "spring:execute", "translation:execute",
                    "generation:execute", "repository:read", "repository:write",
                    "repository:commit", "repository:push", "repository:pr",
                    "modernization:execute", "usage:read", "billing:write"),
            "OPERATOR", Set.of(
                    "workspace:view", "spring:execute", "translation:execute",
                    "generation:execute", "repository:read", "repository:write",
                    "repository:commit", "repository:push", "repository:pr",
                    "modernization:execute", "usage:read", "billing:write", "admin:read", "admin:operate"),
            "APPROVER", Set.of(
                    "workspace:view", "spring:execute", "translation:execute",
                    "generation:execute", "repository:read", "repository:write",
                    "repository:commit", "repository:push", "repository:pr",
                    "modernization:execute", "usage:read", "billing:write", "admin:read", "admin:operate",
                    "admin:approve"),
            "TENANT_ADMIN", KNOWN_PERMISSIONS);

    ControlPlanePrincipal {
        if (!ORGANIZATION.matcher(organizationId).matches()
                || !ACCOUNT.matcher(accountId).matches()
                || !ACTOR.matcher(actorId).matches()) {
            throw new AccessDeniedException("CONTROL_PLANE_PRINCIPAL_INVALID");
        }
        roles = Set.copyOf(roles);
        permissions = Set.copyOf(permissions);
        memberships = Map.copyOf(memberships);
        if (!memberships.containsKey(organizationId)) {
            throw new AccessDeniedException("CONTROL_PLANE_PRIMARY_TENANT_MISSING");
        }
    }

    static Optional<ControlPlanePrincipal> current() {
        var requestAttributes =
                org.springframework.web.context.request.RequestContextHolder.getRequestAttributes();
        if (requestAttributes != null) {
            Object databaseBound = requestAttributes.getAttribute(
                    OidcTenantMembershipFilter.PRINCIPAL_ATTRIBUTE,
                    org.springframework.web.context.request.RequestAttributes.SCOPE_REQUEST);
            if (databaseBound instanceof ControlPlanePrincipal principal) {
                return Optional.of(principal);
            }
        }
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (!(authentication instanceof JwtAuthenticationToken jwt)
                || !authentication.isAuthenticated()) {
            return Optional.empty();
        }
        Object organization = jwt.getToken().getClaims().get("organization_id");
        String organizationId = organization instanceof String value ? value : "";
        Object boundActor = jwt.getToken().getClaims().get("elmos_actor_id");
        String actorId = boundActor instanceof String value
                ? value : jwt.getToken().getSubject();
        String issuer = jwt.getToken().getIssuer() == null
                ? "" : jwt.getToken().getIssuer().toString();
        String accountId = stableAccountId(issuer, jwt.getToken().getSubject());
        Set<String> roles = roles(jwt.getToken().getClaims());
        Set<String> permissions = effectivePermissions(
                roles, explicitPermissions(jwt.getToken().getClaims()));
        Map<String, TenantGrant> memberships = new java.util.LinkedHashMap<>();
        memberships.put(organizationId, new TenantGrant(roles, permissions));
        Object rawMemberships = jwt.getToken().getClaims().get("elmos_tenants");
        if (rawMemberships instanceof Iterable<?> values) {
            for (Object rawMembership : values) {
                if (!(rawMembership instanceof Map<?, ?> membership)) continue;
                Object rawOrganizationId = membership.get("organization_id");
                if (!(rawOrganizationId instanceof String tenantId)
                        || !ORGANIZATION.matcher(tenantId).matches()) {
                    continue;
                }
                Set<String> tenantRoles = rolesFrom(membership.get("roles"));
                Set<String> tenantPermissions = effectivePermissions(
                        tenantRoles, explicitPermissions(membership));
                memberships.put(tenantId, new TenantGrant(
                        tenantRoles, tenantPermissions));
            }
        }
        return Optional.of(new ControlPlanePrincipal(
                organizationId, accountId, actorId, roles, permissions, memberships));
    }

    static ControlPlanePrincipal requireDatabaseBound(
            String requestedOrganizationId,
            String permission
    ) {
        var requestAttributes =
                org.springframework.web.context.request.RequestContextHolder.getRequestAttributes();
        Object bound = requestAttributes == null ? null : requestAttributes.getAttribute(
                OidcTenantMembershipFilter.PRINCIPAL_ATTRIBUTE,
                org.springframework.web.context.request.RequestAttributes.SCOPE_REQUEST);
        if (!(bound instanceof ControlPlanePrincipal principal)) {
            throw new AccessDeniedException("CONTROL_PLANE_DATABASE_PRINCIPAL_REQUIRED");
        }
        if (!principal.organizationId().equals(requestedOrganizationId)) {
            throw new AccessDeniedException("CONTROL_PLANE_PRIMARY_TENANT_MISMATCH");
        }
        principal.require(requestedOrganizationId, principal.actorId(), permission);
        return principal;
    }

    static ControlPlanePrincipal databaseBound(
            String selectedOrganizationId,
            String accountId,
            List<io.elmos.persistence.JdbcOrganizationSelfServiceStore.OrganizationGrant> grants
    ) {
        Map<String, TenantGrant> memberships = new java.util.LinkedHashMap<>();
        for (var grant : grants) {
            Set<String> tenantRoles = databaseRoles(grant.role());
            Set<String> tenantPermissions = databasePermissions(
                    grant.role(), tenantRoles);
            memberships.put(grant.organizationId(),
                    new TenantGrant(tenantRoles, tenantPermissions));
        }
        var selected = grants.stream()
                .filter(grant -> grant.organizationId().equals(selectedOrganizationId))
                .findFirst()
                .orElseThrow(() -> new AccessDeniedException(
                        "CONTROL_PLANE_TENANT_MEMBERSHIP_REQUIRED"));
        TenantGrant primary = memberships.get(selectedOrganizationId);
        return new ControlPlanePrincipal(
                selectedOrganizationId,
                accountId,
                selected.actorId(),
                primary.roles(),
                primary.permissions(),
                memberships);
    }

    /**
     * Deterministic local identity used only when the verified JWT has not yet
     * been rebound through the authoritative account directory. The issuer is
     * part of the key so equal subjects from two identity providers cannot alias.
     */
    static String stableAccountId(String issuer, String subject) {
        if (subject == null || subject.isBlank()) {
            throw new AccessDeniedException("CONTROL_PLANE_SUBJECT_MISSING");
        }
        try {
            String material = (issuer == null ? "" : issuer) + "\u0000" + subject;
            String digest = HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(material.getBytes(StandardCharsets.UTF_8)));
            return "acc-" + digest.substring(0, 40);
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    void require(String requestedOrganizationId, String requestedActorId, String permission) {
        if (!actorId.equals(requestedActorId)) {
            throw new AccessDeniedException("CONTROL_PLANE_SUBJECT_MISMATCH");
        }
        TenantGrant grant = memberships.get(requestedOrganizationId);
        if (grant == null) {
            throw new AccessDeniedException("CONTROL_PLANE_TENANT_MEMBERSHIP_REQUIRED");
        }
        if (!grant.permissions().contains(permission)) {
            throw new AccessDeniedException("CONTROL_PLANE_PERMISSION_REQUIRED");
        }
    }

    String adminRole() {
        return adminRole(organizationId);
    }

    String adminRole(String requestedOrganizationId) {
        TenantGrant grant = memberships.get(requestedOrganizationId);
        if (grant == null) return "";
        if (grant.permissions().contains("admin:approve")) return "APPROVER";
        if (grant.permissions().contains("admin:operate")) return "OPERATOR";
        if (grant.permissions().contains("admin:read")) return "VIEWER";
        return "";
    }

    String auditOrganizationId(String requestedOrganizationId) {
        if (requestedOrganizationId != null
                && memberships.containsKey(requestedOrganizationId)) {
            return requestedOrganizationId;
        }
        return organizationId;
    }

    private static Set<String> roles(Map<String, Object> claims) {
        Object raw = claims.get("roles");
        if (!(raw instanceof Iterable<?>)) {
            Object realm = claims.get("realm_access");
            if (realm instanceof Map<?, ?> values) raw = values.get("roles");
        }
        return rolesFrom(raw);
    }

    private static Set<String> rolesFrom(Object raw) {
        Set<String> result = new LinkedHashSet<>();
        if (raw instanceof Iterable<?> values) {
            values.forEach(value -> {
                String normalized = String.valueOf(value).trim().toUpperCase(Locale.ROOT);
                if (ROLE_PERMISSIONS.containsKey(normalized)) result.add(normalized);
            });
        }
        return result;
    }

    private static Set<String> explicitPermissions(Map<?, ?> claims) {
        List<String> raw = new ArrayList<>();
        Object permissions = claims.get("permissions");
        if (permissions instanceof Iterable<?> values) {
            values.forEach(value -> raw.add(String.valueOf(value)));
        }
        Object scope = claims.get("scope");
        if (scope instanceof String value) raw.addAll(Arrays.asList(value.split("\\s+")));
        Object scp = claims.get("scp");
        if (scp instanceof Iterable<?> values) {
            values.forEach(value -> raw.add(String.valueOf(value)));
        }
        Set<String> result = new LinkedHashSet<>();
        raw.stream()
                .map(String::trim)
                .map(value -> value.startsWith("elmos:") ? value.substring(6) : value)
                .filter(KNOWN_PERMISSIONS::contains)
                .forEach(result::add);
        return result;
    }

    private static Set<String> effectivePermissions(
            Set<String> roles,
            Set<String> explicitPermissions
    ) {
        Set<String> result = new LinkedHashSet<>();
        roles.forEach(role -> result.addAll(
                ROLE_PERMISSIONS.getOrDefault(role, Set.of())));
        result.addAll(explicitPermissions);
        result.retainAll(KNOWN_PERMISSIONS);
        result.add("workspace:view");
        return result;
    }

    private static Set<String> databaseRoles(String memberRole) {
        return switch (memberRole == null ? "" : memberRole.toUpperCase(Locale.ROOT)) {
            case "OWNER", "ADMIN" -> Set.of("TENANT_ADMIN");
            case "MAINTAINER" -> Set.of("MAINTAINER");
            case "MEMBER" -> Set.of("DEVELOPER");
            case "VIEWER", "BILLING" -> Set.of("VIEWER");
            default -> Set.of();
        };
    }

    private static Set<String> databasePermissions(
            String memberRole,
            Set<String> roles
    ) {
        Set<String> result = new LinkedHashSet<>(effectivePermissions(roles, Set.of()));
        if ("BILLING".equalsIgnoreCase(memberRole)) {
            result.add("billing:write");
            result.add("usage:read");
        }
        return Set.copyOf(result);
    }
}
