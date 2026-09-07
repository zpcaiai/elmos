package io.elmos.controlplane;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ControlPlanePrincipalTest {
    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void grantsAdministratorPermissionsOnlyToTheVerifiedExactEmail() {
        authenticate(Map.of(
                "sub", "user:operator",
                "organization_id", "tenant-a",
                "email", "ZPCHONEY@GMAIL.COM",
                "email_verified", true,
                "roles", List.of("OPERATOR")
        ));

        ControlPlanePrincipal principal = ControlPlanePrincipal.current().orElseThrow();

        principal.require("tenant-a", "user:operator", "repository:write");
        principal.require("tenant-a", "user:operator", "admin:operate");
        assertEquals("APPROVER", principal.adminRole());
        assertTrue(principal.platformAdministrator());
        assertTrue(principal.permissions().contains("translation:execute"));
    }

    @Test
    void deniesCrossTenantAndMissingApprovalPermission() {
        authenticate(Map.of(
                "sub", "user:viewer",
                "organization_id", "tenant-a",
                "roles", List.of("VIEWER")
        ));

        ControlPlanePrincipal principal = ControlPlanePrincipal.current().orElseThrow();

        assertThrows(AccessDeniedException.class, () ->
                principal.require("tenant-b", "user:viewer", "repository:read"));
        assertThrows(AccessDeniedException.class, () ->
                principal.require("tenant-a", "user:viewer", "admin:approve"));
        assertEquals("", principal.adminRole());
    }

    @Test
    void ignoresUnknownRolesAndPermissions() {
        authenticate(Map.of(
                "sub", "user:limited",
                "organization_id", "tenant-a",
                "roles", List.of("ROOT", "UNKNOWN"),
                "permissions", List.of("*", "root:host", "elmos:repository:read")
        ));

        ControlPlanePrincipal principal = ControlPlanePrincipal.current().orElseThrow();

        principal.require("tenant-a", "user:limited", "repository:read");
        assertThrows(AccessDeniedException.class, () ->
                principal.require("tenant-a", "user:limited", "repository:write"));
    }

    @Test
    void keepsBusinessPermissionsTenantScopedWhileApplyingTheExactAdminBoundary() {
        authenticate(Map.of(
                "sub", "user:multi-tenant",
                "organization_id", "tenant-a",
                "email", "zpchoney@gmail.com",
                "email_verified", true,
                "roles", List.of("VIEWER"),
                "elmos_tenants", List.of(
                        Map.of(
                                "organization_id", "tenant-b",
                                "roles", List.of("OPERATOR"),
                                "permissions", List.of("elmos:repository:push")),
                        Map.of(
                                "organization_id", "tenant-c",
                                "roles", List.of("VIEWER"))
                )
        ));

        ControlPlanePrincipal principal = ControlPlanePrincipal.current().orElseThrow();

        principal.require("tenant-b", "user:multi-tenant", "admin:operate");
        principal.require("tenant-b", "user:multi-tenant", "repository:push");
        assertEquals("APPROVER", principal.adminRole("tenant-b"));
        assertEquals("tenant-b", principal.auditOrganizationId("tenant-b"));
        assertEquals("tenant-a", principal.auditOrganizationId("tenant-d"));
        assertEquals("APPROVER", principal.adminRole("tenant-c"));
        assertThrows(AccessDeniedException.class, () ->
                principal.require("tenant-c", "user:multi-tenant", "repository:push"));
        assertThrows(AccessDeniedException.class, () ->
                principal.require("tenant-d", "user:multi-tenant", "workspace:view"));
    }

    @Test
    void stripsForgedAdministratorClaimsFromEveryOtherOrUnverifiedEmail() {
        for (Map<String, Object> identity : List.of(
                Map.<String, Object>of(
                        "email", "other@example.com", "email_verified", true),
                Map.<String, Object>of(
                        "email", "zpchoney@gmail.com", "email_verified", false),
                Map.<String, Object>of(
                        "email", "zpchoney+alias@gmail.com", "email_verified", true))) {
            Map<String, Object> claims = new java.util.LinkedHashMap<>(identity);
            claims.put("sub", "user:forged-admin");
            claims.put("organization_id", "tenant-a");
            claims.put("roles", List.of("TENANT_ADMIN"));
            claims.put("permissions", List.of(
                    "admin:read", "admin:operate", "admin:approve", "configuration:manage"));
            authenticate(claims);

            ControlPlanePrincipal principal = ControlPlanePrincipal.current().orElseThrow();

            assertEquals("", principal.adminRole());
            assertTrue(!principal.platformAdministrator());
            assertThrows(AccessDeniedException.class, () ->
                    principal.require("tenant-a", "user:forged-admin", "admin:read"));
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void directConstructionCannotBypassTheAdministratorBoundary() {
        var forged = new ControlPlanePrincipal.TenantGrant(
                Set.of("TENANT_ADMIN"),
                Set.of("workspace:view", "admin:read", "admin:operate"));

        ControlPlanePrincipal principal = new ControlPlanePrincipal(
                "tenant-a",
                "user:forged-admin",
                false,
                forged.roles(),
                forged.permissions(),
                Map.of("tenant-a", forged));

        assertEquals(Set.of("workspace:view"), principal.permissions());
        assertTrue(principal.roles().isEmpty());
        assertThrows(AccessDeniedException.class, () ->
                principal.require("tenant-a", "user:forged-admin", "admin:read"));
    }

    private static void authenticate(Map<String, Object> claims) {
        Instant now = Instant.now();
        Jwt.Builder builder = Jwt.withTokenValue("verified-by-test-decoder")
                .header("alg", "RS256")
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300));
        claims.forEach(builder::claim);
        SecurityContextHolder.getContext().setAuthentication(
                new JwtAuthenticationToken(
                        builder.build(),
                        List.of(new SimpleGrantedAuthority("ROLE_TEST"))));
    }
}
