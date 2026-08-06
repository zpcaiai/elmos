package io.elmos.controlplane;

import io.elmos.proofloop.ModernizationProofLoopEngine;
import io.elmos.proofloop.SkillContractCatalog;
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

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ModernizationProofContractControllerTest {
    private final SkillContractCatalog catalog = new SkillContractCatalog();
    private final ModernizationProofContractController controller =
            new ModernizationProofContractController(catalog, new ModernizationProofLoopEngine());

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void exposesTheExactCatalogToAnAuthorizedTenant() {
        authenticate("tenant-a", "developer-a", "DEVELOPER");

        var contracts = controller.contracts();

        assertEquals(64, contracts.size());
        assertEquals("B105-S01", contracts.getFirst().get("id"));
        assertEquals("B108-S16", contracts.getLast().get("id"));
        assertTrue(contracts.stream().allMatch(contract -> contract.containsKey("canonicalSha256")));
    }

    @Test
    void derivesTheSubjectTenantFromAuthentication() {
        authenticate("tenant-authenticated", "developer-a", "DEVELOPER");

        var response = controller.subjectDigest(new ModernizationProofContractController.SubjectDigestRequest(
                "project-a", "repository-a", "a".repeat(40), "b".repeat(40), null,
                "sha256:" + "0".repeat(64)));

        assertEquals("tenant-authenticated", response.get("organizationId"));
        assertTrue(String.valueOf(response.get("subjectDigest")).matches("sha256:[0-9a-f]{64}"));
    }

    @Test
    void deniesAViewerWithoutExecutionPermission() {
        authenticate("tenant-a", "viewer-a", "VIEWER");

        assertThrows(AccessDeniedException.class, controller::contracts);
    }

    private static void authenticate(String organizationId, String subject, String role) {
        Instant now = Instant.now();
        Jwt jwt = Jwt.withTokenValue("verified-by-test-decoder")
                .header("alg", "RS256")
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300))
                .claim("sub", subject)
                .claim("organization_id", organizationId)
                .claim("roles", List.of(role))
                .build();
        SecurityContextHolder.getContext().setAuthentication(new JwtAuthenticationToken(
                jwt, List.of(new SimpleGrantedAuthority("ROLE_TEST"))));
    }
}
