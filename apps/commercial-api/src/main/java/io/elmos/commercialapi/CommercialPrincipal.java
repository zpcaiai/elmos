package io.elmos.commercialapi;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;

import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

public record CommercialPrincipal(String organizationId, String actorId, Set<String> scopes) {
    private static final Pattern ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");
    private static final String PLATFORM_ADMINISTRATOR_EMAIL = "zpchoney@gmail.com";

    public CommercialPrincipal {
        if (!valid(organizationId) || !valid(actorId)) {
            throw new AccessDeniedException("COMMERCIAL_PRINCIPAL_INVALID");
        }
        scopes = Set.copyOf(scopes);
    }

    public static CommercialPrincipal from(Jwt jwt) {
        if (jwt == null) throw new AccessDeniedException("COMMERCIAL_AUTHENTICATION_REQUIRED");
        String organizationId = claim(jwt, "organization_id");
        String actorId = jwt.getSubject();
        Set<String> scopes = new LinkedHashSet<>();
        Object rawScope = jwt.getClaims().get("scope");
        if (rawScope instanceof String value) {
            Arrays.stream(value.split("\\s+")).filter(item -> !item.isBlank()).forEach(scopes::add);
        }
        Object rawScopes = jwt.getClaims().get("scp");
        if (rawScopes instanceof Iterable<?> values) {
            values.forEach(value -> scopes.add(String.valueOf(value)));
        }
        if (!isPlatformAdministrator(jwt)) {
            scopes.removeIf(CommercialPrincipal::isAdministratorScope);
        }
        return new CommercialPrincipal(organizationId, actorId, scopes);
    }

    public void requireOrganization(String requestedOrganizationId) {
        if (!organizationId.equals(requestedOrganizationId)) {
            throw new AccessDeniedException("COMMERCIAL_CROSS_TENANT_DENIED");
        }
    }

    public void requireScope(String requiredScope) {
        if (!scopes.contains(requiredScope)) {
            throw new AccessDeniedException("COMMERCIAL_SCOPE_REQUIRED");
        }
    }

    private static String claim(Jwt jwt, String name) {
        Object value = jwt.getClaims().get(name);
        return value instanceof String text ? text : "";
    }

    private static boolean isPlatformAdministrator(Jwt jwt) {
        Object emailVerified = jwt.getClaims().get("email_verified");
        Object email = jwt.getClaims().get("email");
        return Boolean.TRUE.equals(emailVerified)
                && email instanceof String value
                && PLATFORM_ADMINISTRATOR_EMAIL.equals(
                        value.trim().toLowerCase(Locale.ROOT));
    }

    private static boolean isAdministratorScope(String scope) {
        return scope.startsWith("commercial:") && scope.endsWith(":admin");
    }

    private static boolean valid(String value) {
        return value != null && ID.matcher(value).matches();
    }
}
