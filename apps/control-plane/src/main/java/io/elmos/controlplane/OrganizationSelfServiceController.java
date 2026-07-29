package io.elmos.controlplane;

import io.elmos.identity.Destinations;
import io.elmos.identity.Secrets;
import io.elmos.persistence.JdbcOrganizationSelfServiceStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

/**
 * OIDC-backed account and organization self-service.
 *
 * <p>Account identity comes only from the verified JWT. Organization mutations
 * are independently re-authorized by the database membership directory.</p>
 */
@RestController
@RequestMapping("/api/v1/account")
public class OrganizationSelfServiceController {
    private static final int INVITATION_TTL_SECONDS = 72 * 60 * 60;

    private final JdbcOrganizationSelfServiceStore organizations;
    private final String pepperFile;

    public OrganizationSelfServiceController(
            JdbcOrganizationSelfServiceStore organizations,
            @Value("${elmos.identity.local.pepper-file:}") String pepperFile
    ) {
        this.organizations = organizations;
        this.pepperFile = pepperFile;
    }

    public record CreateOrganizationRequest(String displayName, String dataRegion) {
    }

    public record InvitationRequest(String email, String role) {
    }

    public record AcceptInvitationRequest(String token) {
    }

    public record UpdateMemberRequest(String role) {
    }

    private record OidcIdentity(
            String accountId,
            String issuer,
            String subject,
            String email,
            String displayName
    ) {
    }

    @GetMapping("/organizations")
    public ResponseEntity<?> organizations() {
        OidcIdentity identity = identity();
        return ResponseEntity.ok(Map.of(
                "accountId", identity.accountId(),
                "organizations", organizations.organizations(identity.accountId())));
    }

    @PostMapping("/organizations")
    public ResponseEntity<?> createOrganization(
            @RequestBody CreateOrganizationRequest request
    ) {
        OidcIdentity identity = identity();
        String displayName = bounded(request.displayName(), 2, 128, "ELMOS_ORGANIZATION_NAME_INVALID");
        String region = request.dataRegion() == null || request.dataRegion().isBlank()
                ? "cn-north"
                : bounded(request.dataRegion(), 2, 32, "ELMOS_DATA_REGION_INVALID");
        if (!region.matches("^[a-z][a-z0-9-]{1,31}$")) {
            throw new BadRequest("ELMOS_DATA_REGION_INVALID");
        }
        String organizationId = "org-" + UUID.randomUUID();
        String actorId = actorId(organizationId, identity.accountId());
        organizations.createOrganization(
                identity.accountId(), organizationId, displayName, actorId, region,
                sha256(identity.issuer() + "\u0000" + identity.subject()));
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
                "organizationId", organizationId,
                "displayName", displayName,
                "role", "OWNER",
                "actorId", actorId));
    }

    @PostMapping("/organizations/{organizationId}/invitations")
    public ResponseEntity<?> invite(
            @PathVariable String organizationId,
            @RequestBody InvitationRequest request
    ) {
        OidcIdentity identity = identity();
        JdbcOrganizationSelfServiceStore.OrganizationGrant grant =
                organizations.organizations(identity.accountId()).stream()
                        .filter(candidate -> candidate.organizationId().equals(organizationId))
                        .filter(candidate -> java.util.Set.of("OWNER", "ADMIN")
                                .contains(candidate.role()))
                        .findFirst()
                        .orElseThrow(() -> new AccessDeniedException(
                                "ELMOS_ORGANIZATION_ADMIN_REQUIRED"));
        Destinations.Destination destination = Destinations.normalizeEmail(request.email())
                .orElseThrow(() -> new BadRequest("ELMOS_INVITATION_EMAIL_INVALID"));
        String role = request.role() == null ? "" : request.role().trim().toUpperCase(Locale.ROOT);
        if (!java.util.Set.of("ADMIN", "MAINTAINER", "MEMBER", "BILLING", "VIEWER").contains(role)) {
            throw new BadRequest("ELMOS_INVITATION_ROLE_INVALID");
        }
        String invitationId = "invite-" + UUID.randomUUID();
        String token = Secrets.newOpaqueToken();
        String pepper = OwnerOnlySecretFile.readRequired(
                pepperFile, 32, 4096, "ELMOS_IDENTITY_PEPPER_FILE_INVALID");
        organizations.createInvitation(
                invitationId, organizationId, identity.accountId(), grant.actorId(),
                Secrets.lookupHmac(pepper, destination.normalized()), destination.masked(),
                role, Secrets.sha256Hex(token), INVITATION_TTL_SECONDS);
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
                "invitationId", invitationId,
                "status", "PENDING",
                "destination", destination.masked(),
                "role", role,
                // Returned exactly once. The database stores only SHA-256.
                "invitationToken", token,
                "expiresInSeconds", INVITATION_TTL_SECONDS));
    }

    @PostMapping("/invitations/accept")
    public ResponseEntity<?> accept(@RequestBody AcceptInvitationRequest request) {
        OidcIdentity identity = identity();
        String token = bounded(request.token(), 32, 512, "ELMOS_INVITATION_TOKEN_INVALID");
        String tokenHash = Secrets.sha256Hex(token);
        String organizationId = organizations.invitationOrganization(tokenHash)
                .orElseThrow(() -> new NotFound("ELMOS_INVITATION_UNKNOWN"));
        String pepper = OwnerOnlySecretFile.readRequired(
                pepperFile, 32, 4096, "ELMOS_IDENTITY_PEPPER_FILE_INVALID");
        String destinationHmac = Secrets.lookupHmac(pepper, identity.email());
        String actorId = actorId(organizationId, identity.accountId());
        organizations.acceptInvitation(
                tokenHash, destinationHmac, identity.accountId(), actorId);
        return ResponseEntity.ok(Map.of(
                "organizationId", organizationId,
                "actorId", actorId,
                "status", "ACCEPTED"));
    }

    @GetMapping("/organizations/{organizationId}/members")
    public ResponseEntity<?> members(@PathVariable String organizationId) {
        OidcIdentity identity = identity();
        return ResponseEntity.ok(Map.of(
                "members", organizations.members(organizationId, identity.accountId())));
    }

    @PatchMapping("/organizations/{organizationId}/members/{accountId}")
    public ResponseEntity<?> updateMember(
            @PathVariable String organizationId,
            @PathVariable String accountId,
            @RequestBody UpdateMemberRequest request
    ) {
        OidcIdentity identity = identity();
        String role = request.role() == null ? "" : request.role().trim().toUpperCase(Locale.ROOT);
        organizations.updateMember(organizationId, identity.accountId(), accountId, role, false);
        return ResponseEntity.ok(Map.of("status", "UPDATED", "accountId", accountId, "role", role));
    }

    @DeleteMapping("/organizations/{organizationId}/members/{accountId}")
    public ResponseEntity<?> removeMember(
            @PathVariable String organizationId,
            @PathVariable String accountId
    ) {
        OidcIdentity identity = identity();
        organizations.updateMember(organizationId, identity.accountId(), accountId, "VIEWER", true);
        return ResponseEntity.ok(Map.of("status", "REMOVED", "accountId", accountId));
    }

    private OidcIdentity identity() {
        if (!(SecurityContextHolder.getContext().getAuthentication()
                instanceof JwtAuthenticationToken authentication)
                || !authentication.isAuthenticated()) {
            throw new AccessDeniedException("CONTROL_PLANE_AUTH_REQUIRED");
        }
        String issuer = authentication.getToken().getIssuer() == null
                ? "" : authentication.getToken().getIssuer().toString();
        String subject = authentication.getToken().getSubject();
        Object verified = authentication.getToken().getClaims().get("email_verified");
        String email = String.valueOf(authentication.getToken().getClaims().getOrDefault("email", ""));
        Destinations.Destination normalized = Destinations.normalizeEmail(email)
                .orElseThrow(() -> new AccessDeniedException("ELMOS_OIDC_VERIFIED_EMAIL_REQUIRED"));
        if (!Boolean.TRUE.equals(verified)) {
            throw new AccessDeniedException("ELMOS_OIDC_VERIFIED_EMAIL_REQUIRED");
        }
        String displayName = firstNonBlank(
                authentication.getToken().getClaimAsString("name"),
                authentication.getToken().getClaimAsString("preferred_username"),
                normalized.masked());
        String accountId = "acc-" + sha256(issuer + "\u0000" + subject).substring(0, 40);
        organizations.resolveOidcAccount(
                accountId, issuer, subject, normalized.normalized(), true, displayName);
        return new OidcIdentity(
                accountId, issuer, subject, normalized.normalized(), displayName);
    }

    private static String actorId(String organizationId, String accountId) {
        return "actor-" + sha256(organizationId + ":" + accountId).substring(0, 32);
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private static String bounded(String value, int minimum, int maximum, String code) {
        String candidate = value == null ? "" : value.trim();
        if (candidate.length() < minimum || candidate.length() > maximum) {
            throw new BadRequest(code);
        }
        return candidate;
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) return value;
        }
        return "ELMOS User";
    }

    static final class BadRequest extends RuntimeException {
        private static final long serialVersionUID = 1L;
        private final String code;

        BadRequest(String code) {
            super("Request rejected");
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    static final class NotFound extends RuntimeException {
        private static final long serialVersionUID = 1L;
        private final String code;

        NotFound(String code) {
            super("Resource not found");
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    @ExceptionHandler(BadRequest.class)
    ResponseEntity<?> badRequest(BadRequest error) {
        return ResponseEntity.badRequest().body(Map.of("status", "ERROR", "code", error.code()));
    }

    @ExceptionHandler(NotFound.class)
    ResponseEntity<?> notFound(NotFound error) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("status", "ERROR", "code", error.code()));
    }

    @ExceptionHandler(JdbcOrganizationSelfServiceStore.OrganizationStoreException.class)
    ResponseEntity<?> storeError(JdbcOrganizationSelfServiceStore.OrganizationStoreException error) {
        HttpStatus status = switch (error.code()) {
            case "ELMOS_ORGANIZATION_ADMIN_REQUIRED" -> HttpStatus.FORBIDDEN;
            case "ELMOS_INVITATION_UNKNOWN", "ELMOS_ORGANIZATION_MEMBER_UNKNOWN" -> HttpStatus.NOT_FOUND;
            case "ELMOS_IDENTITY_CONFLICT", "ELMOS_IDENTITY_LINK_REQUIRED",
                 "ELMOS_INVITATION_NOT_PENDING" -> HttpStatus.CONFLICT;
            default -> HttpStatus.BAD_REQUEST;
        };
        return ResponseEntity.status(status)
                .body(Map.of("status", "ERROR", "code", error.code()));
    }
}
