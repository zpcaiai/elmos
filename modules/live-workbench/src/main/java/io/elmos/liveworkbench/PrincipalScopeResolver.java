package io.elmos.liveworkbench;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

import java.util.Set;
import java.util.stream.Collectors;

import static io.elmos.liveworkbench.ProductionContracts.PrincipalScope;

/** Derives immutable tenant/account/actor scope exclusively from a verified JWT. */
@Component
public final class PrincipalScopeResolver {
    public PrincipalScope resolve(Authentication authentication) {
        if (!(authentication instanceof JwtAuthenticationToken token) || !token.isAuthenticated())
            throw LiveWorkbenchException.denied("VERIFIED_JWT_REQUIRED");
        String tenant = claim(token, "tenant_id");
        String account = claim(token, "account_id");
        String environment = claim(token, "environment_id");
        String actor = token.getToken().getSubject();
        if (actor == null || actor.isBlank()) throw LiveWorkbenchException.denied("JWT_SUBJECT_REQUIRED");
        Set<String> authorities = token.getAuthorities().stream().map(GrantedAuthority::getAuthority)
                .map(value -> value.startsWith("SCOPE_") ? value.substring(6) : value)
                .collect(Collectors.toUnmodifiableSet());
        return new PrincipalScope(tenant, account, actor, environment, authorities);
    }

    private static String claim(JwtAuthenticationToken token, String name) {
        Object raw = token.getToken().getClaims().get(name);
        if (!(raw instanceof String value) || value.isBlank())
            throw LiveWorkbenchException.denied("JWT_" + name.toUpperCase(java.util.Locale.ROOT) + "_REQUIRED");
        return value;
    }
}
