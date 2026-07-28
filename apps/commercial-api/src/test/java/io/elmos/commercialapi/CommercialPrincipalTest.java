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
