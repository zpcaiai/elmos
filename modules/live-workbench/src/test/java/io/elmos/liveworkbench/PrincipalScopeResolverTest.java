package io.elmos.liveworkbench;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class PrincipalScopeResolverTest {
    @Test void derivesEveryScopeDimensionFromVerifiedJwtClaims() {
        Jwt jwt = Jwt.withTokenValue("verified-token").header("alg", "none")
                .subject("actor-a").claim("tenant_id", "tenant-a").claim("account_id", "account-a")
                .claim("environment_id", "env-a").issuedAt(Instant.now()).expiresAt(Instant.now().plusSeconds(60)).build();
        JwtAuthenticationToken authentication = new JwtAuthenticationToken(jwt,
                List.of(new SimpleGrantedAuthority("SCOPE_workbench.session.read")));
        var scope = new PrincipalScopeResolver().resolve(authentication);
        assertEquals("tenant-a", scope.tenantId());
        assertEquals("account-a", scope.accountId());
        assertEquals("actor-a", scope.actorId());
        assertTrue(scope.has("workbench.session.read"));
    }

    @Test void missingTenantClaimFailsClosed() {
        Jwt jwt = Jwt.withTokenValue("verified-token").header("alg", "none").subject("actor-a")
                .claim("account_id", "account-a").claim("environment_id", "env-a")
                .issuedAt(Instant.now()).expiresAt(Instant.now().plusSeconds(60)).build();
        assertThrows(LiveWorkbenchException.class,
                () -> new PrincipalScopeResolver().resolve(new JwtAuthenticationToken(jwt)));
    }
}
