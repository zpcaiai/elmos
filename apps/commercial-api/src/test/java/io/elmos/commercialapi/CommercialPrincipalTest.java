package io.elmos.commercialapi;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CommercialPrincipalTest {
    @Test
    void exactTenantAndScopeAreRequired() {
        CommercialPrincipal principal = CommercialPrincipal.from(jwt(
                "actor-1",
                Map.of("organization_id", "org-a", "scope", "billing:read billing:write")));

        assertEquals("org-a", principal.organizationId());
        assertDoesNotThrow(() -> principal.requireOrganization("org-a"));
        assertDoesNotThrow(() -> principal.requireScope("billing:write"));
        assertThrows(AccessDeniedException.class, () -> principal.requireOrganization("org-b"));
        assertThrows(AccessDeniedException.class, () -> principal.requireScope("billing:admin"));
    }

    @Test
    void anonymousMalformedAndMissingTenantClaimsFailClosed() {
        assertThrows(AccessDeniedException.class, () -> CommercialPrincipal.from(null));
        assertThrows(AccessDeniedException.class, () -> CommercialPrincipal.from(jwt(
                "actor-1",
                Map.of("scope", "billing:read"))));
        assertThrows(AccessDeniedException.class, () -> CommercialPrincipal.from(jwt(
                "../actor",
                Map.of("organization_id", "org-a", "scope", "billing:read"))));
    }

    @Test
    void listStyleScopesAreSupportedWithoutBroadening() {
        CommercialPrincipal principal = CommercialPrincipal.from(jwt(
                "actor-1",
                Map.of("organization_id", "org-a", "scp", List.of("usage:read"))));

        assertDoesNotThrow(() -> principal.requireScope("usage:read"));
        assertThrows(AccessDeniedException.class, () -> principal.requireScope("usage:write"));
    }

    @Test
    void verifiedExactAdministratorRetainsCommercialAdminScopes() {
        CommercialPrincipal principal = CommercialPrincipal.from(jwt(
                "actor-admin",
                Map.of(
                        "organization_id", "org-a",
                        "email", " ZPCHONEY@GMAIL.COM ",
                        "email_verified", true,
                        "scope", "commercial:billing:admin commercial:billing:write",
                        "scp", List.of("commercial:usage:admin"))));

        assertDoesNotThrow(() -> principal.requireScope("commercial:billing:admin"));
        assertDoesNotThrow(() -> principal.requireScope("commercial:usage:admin"));
        assertDoesNotThrow(() -> principal.requireScope("commercial:billing:write"));
    }

    @Test
    void stripsCommercialAdminScopesFromEveryOtherOrUnverifiedEmail() {
        for (Map<String, Object> identity : List.of(
                Map.<String, Object>of("email", "other@example.com", "email_verified", true),
                Map.<String, Object>of("email", "zpchoney@gmail.com", "email_verified", false),
                Map.<String, Object>of("email", "zpchoney+alias@gmail.com", "email_verified", true),
                Map.<String, Object>of("email", "zpchoney@gmail.com", "email_verified", "true"),
                Map.<String, Object>of("email_verified", true))) {
            Map<String, Object> claims = new java.util.LinkedHashMap<>(identity);
            claims.put("organization_id", "org-a");
            claims.put("scope", "commercial:billing:admin commercial:billing:write");
            claims.put("scp", List.of("commercial:usage:admin", "commercial:usage:read"));

            CommercialPrincipal principal = CommercialPrincipal.from(jwt("actor-user", claims));

            assertThrows(AccessDeniedException.class, () ->
                    principal.requireScope("commercial:billing:admin"));
            assertThrows(AccessDeniedException.class, () ->
                    principal.requireScope("commercial:usage:admin"));
            assertDoesNotThrow(() -> principal.requireScope("commercial:billing:write"));
            assertDoesNotThrow(() -> principal.requireScope("commercial:usage:read"));
        }
    }

    private static Jwt jwt(String subject, Map<String, Object> claims) {
        return new Jwt(
                "encoded",
                Instant.parse("2026-07-28T00:00:00Z"),
                Instant.parse("2026-07-28T01:00:00Z"),
                Map.of("alg", "RS256"),
                new java.util.LinkedHashMap<>() {{
                    put("sub", subject);
                    putAll(claims);
                }}
        );
    }
}
