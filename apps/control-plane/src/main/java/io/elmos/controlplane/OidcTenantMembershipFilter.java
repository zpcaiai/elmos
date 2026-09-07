package io.elmos.controlplane;

import io.elmos.identity.Destinations;
import io.elmos.persistence.JdbcOrganizationSelfServiceStore;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

/**
 * Resolves a requested tenant against the authoritative membership directory.
 *
 * <p>The tenant header is a selector, never an assertion. Its membership and
 * actor are loaded from PostgreSQL after JWT authentication. This lets an
 * organization created or joined through self-service become usable immediately,
 * without waiting for an external IdP to copy ELMOS membership state into a new
 * token. A selected tenant that is absent or removed fails closed.</p>
 */
final class OidcTenantMembershipFilter extends OncePerRequestFilter {
    static final String PRINCIPAL_ATTRIBUTE =
            OidcTenantMembershipFilter.class.getName() + ".principal";

    private final JdbcOrganizationSelfServiceStore organizations;

    OidcTenantMembershipFilter(JdbcOrganizationSelfServiceStore organizations) {
        this.organizations = organizations;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String requestedOrganization = request.getHeader("X-ELMOS-Organization-ID");
        if (requestedOrganization == null || requestedOrganization.isBlank()) {
            filterChain.doFilter(request, response);
            return;
        }
        if (!(SecurityContextHolder.getContext().getAuthentication()
                instanceof JwtAuthenticationToken authentication)
                || !authentication.isAuthenticated()) {
            filterChain.doFilter(request, response);
            return;
        }
        try {
            if (!requestedOrganization.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
                throw new AccessDeniedException("CONTROL_PLANE_TENANT_SELECTOR_INVALID");
            }

            String issuer = authentication.getToken().getIssuer() == null
                    ? "" : authentication.getToken().getIssuer().toString();
            String subject = authentication.getToken().getSubject();
            Object verified = authentication.getToken().getClaims().get("email_verified");
            String email = String.valueOf(
                    authentication.getToken().getClaims().getOrDefault("email", ""));
            Destinations.Destination normalized = Destinations.normalizeEmail(email)
                    .orElseThrow(() -> new AccessDeniedException(
                            "ELMOS_OIDC_VERIFIED_EMAIL_REQUIRED"));
            if (!Boolean.TRUE.equals(verified)) {
                throw new AccessDeniedException("ELMOS_OIDC_VERIFIED_EMAIL_REQUIRED");
            }
            String accountId = "acc-" + sha256(
                    issuer + "\u0000" + subject).substring(0, 40);
            String displayName = authentication.getToken().getClaimAsString("name");
            organizations.resolveOidcAccount(
                    accountId,
                    issuer,
                    subject,
                    normalized.normalized(),
                    true,
                    displayName == null || displayName.isBlank()
                            ? normalized.masked() : displayName);
            request.setAttribute(
                    PRINCIPAL_ATTRIBUTE,
                    ControlPlanePrincipal.databaseBound(
                            requestedOrganization,
                            subject,
                            ControlPlanePrincipal.isPlatformAdministratorEmail(
                                    normalized.normalized(), true),
                            organizations.organizations(accountId)));
        } catch (AccessDeniedException
                 | JdbcOrganizationSelfServiceStore.OrganizationStoreException rejected) {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setContentType("application/json");
            response.getWriter().write(
                    "{\"status\":\"ERROR\",\"code\":\"CONTROL_PLANE_TENANT_MEMBERSHIP_REQUIRED\"}");
            return;
        }
        filterChain.doFilter(request, response);
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }
}
