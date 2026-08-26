package io.elmos.controlplane;

import io.elmos.persistence.JdbcOrganizationSelfServiceStore;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ControlPlanePrincipalTest {
    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void derivesTenantActorAndOperatorPermissionsFromVerifiedJwt() {
        authenticate(Map.of(
                "sub", "user:operator",
                "organization_id", "tenant-a",
                "roles", List.of("OPERATOR")
        ));

        ControlPlanePrincipal principal = ControlPlanePrincipal.current().orElseThrow();

        principal.require("tenant-a", "user:operator", "repository:write");
        principal.require("tenant-a", "user:operator", "admin:operate");
        assertEquals("OPERATOR", principal.adminRole());
        assertEquals(
                ControlPlanePrincipal.stableAccountId(
                        "https://identity.example.test", "user:operator"),
                principal.accountId());
        assertTrue(principal.permissions().contains("translation:execute"));
    }

    @Test
    void databaseMembershipBindsCanonicalAccountAndOrganizationActor() {
        ControlPlanePrincipal principal = ControlPlanePrincipal.databaseBound(
                "tenant-a",
                "acc-canonical-1",
                List.of(
                        new JdbcOrganizationSelfServiceStore.OrganizationGrant(
                                "tenant-a", "Tenant A", "MAINTAINER", "actor-canonical-a"),
                        new JdbcOrganizationSelfServiceStore.OrganizationGrant(
                                "tenant-b", "Tenant B", "VIEWER", "actor-canonical-b")));

        assertEquals("acc-canonical-1", principal.accountId());
        assertEquals("actor-canonical-a", principal.actorId());
        principal.require("tenant-a", "actor-canonical-a", "repository:push");
        assertThrows(AccessDeniedException.class, () ->
                principal.require("tenant-a", "raw-oidc-subject", "repository:push"));
    }

    @Test
    void oidcFilterUsesResolvedAccountAndSelectedGrantActor() throws Exception {
        JdbcOrganizationSelfServiceStore organizations =
                mock(JdbcOrganizationSelfServiceStore.class);
        String proposed = ControlPlanePrincipal.stableAccountId(
                "https://identity.example.test", "raw-oidc-subject");
        when(organizations.resolveOidcAccount(
                proposed,
                "https://identity.example.test",
                "raw-oidc-subject",
                "User@example.test",
                true,
                "Canonical User"))
                .thenReturn("acc-existing-canonical");
        when(organizations.organizations("acc-existing-canonical"))
                .thenReturn(List.of(
                        new JdbcOrganizationSelfServiceStore.OrganizationGrant(
                                "tenant-a", "Tenant A", "MEMBER", "actor-membership-a")));
        authenticate(Map.of(
                "sub", "raw-oidc-subject",
                "organization_id", "tenant-a",
                "roles", List.of("DEVELOPER"),
                "email", "User@Example.Test",
                "email_verified", true,
                "name", "Canonical User"));
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-ELMOS-Organization-ID", "tenant-a");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<ControlPlanePrincipal> bound = new AtomicReference<>();

        new OidcTenantMembershipFilter(organizations).doFilter(
                request,
                response,
                (servletRequest, servletResponse) -> bound.set(
                        (ControlPlanePrincipal) servletRequest.getAttribute(
                                OidcTenantMembershipFilter.PRINCIPAL_ATTRIBUTE)));

        assertEquals(200, response.getStatus());
        assertEquals("acc-existing-canonical", bound.get().accountId());
        assertEquals("actor-membership-a", bound.get().actorId());
        verify(organizations).organizations("acc-existing-canonical");
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
    void authorizesOnlyTheRolesDeclaredForTheSelectedTenantMembership() {
        authenticate(Map.of(
                "sub", "user:multi-tenant",
                "organization_id", "tenant-a",
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
        assertEquals("OPERATOR", principal.adminRole("tenant-b"));
        assertEquals("tenant-b", principal.auditOrganizationId("tenant-b"));
        assertEquals("tenant-a", principal.auditOrganizationId("tenant-d"));
        assertEquals("", principal.adminRole("tenant-c"));
        assertThrows(AccessDeniedException.class, () ->
                principal.require("tenant-c", "user:multi-tenant", "repository:push"));
        assertThrows(AccessDeniedException.class, () ->
                principal.require("tenant-d", "user:multi-tenant", "workspace:view"));
    }

    private static void authenticate(Map<String, Object> claims) {
        Instant now = Instant.now();
        Jwt.Builder builder = Jwt.withTokenValue("verified-by-test-decoder")
                .header("alg", "RS256")
                .issuer("https://identity.example.test")
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300));
        claims.forEach(builder::claim);
        SecurityContextHolder.getContext().setAuthentication(
                new JwtAuthenticationToken(
                        builder.build(),
                        List.of(new SimpleGrantedAuthority("ROLE_TEST"))));
    }
}
