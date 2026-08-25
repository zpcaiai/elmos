package io.elmos.controlplane;

import io.elmos.commercial.PlatformAdminPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.util.Map;

/**
 * The cross-tenant administration API.
 *
 * <h2>Why the administrator identity comes from a header</h2>
 *
 * <p>Same shape as the existing operations-observability endpoints, which take
 * {@code X-ELMOS-Actor-ID} and {@code X-ELMOS-Organization-ID} from the console
 * BFF after it has authenticated the session. This is an internal API: it is not
 * reachable from a browser, and the BFF is what proves who is calling.
 *
 * <p>The organization header is still required, but it means something
 * different here. On the operations endpoints it names the tenant being acted
 * on. Here it names the administrator's OWN tenant, and is used only to resolve
 * which account is calling -- the tenant being read is a path variable or a
 * filter, and may be any of them. Reading that header as "the tenant to act on"
 * is the mistake this paragraph exists to prevent.
 *
 * <p>Authorization is therefore not "does this actor belong to the tenant they
 * named" but "is this account on the platform administrator list", and that
 * question is answered in the database. This controller deliberately contains
 * no authorization logic of its own: a second opinion in Java would be a second
 * thing to keep in step, and the one in the database is the one that also
 * writes the audit row.
 */
@RestController
@RequestMapping("/api/v1/platform-admin")
public class PlatformAdminController {

    // The same two headers the existing operations endpoints already receive
    // from the console BFF. There is deliberately no new header and no new
    // identity concept: the account is derived from these, not asserted by the
    // caller -- a caller that could name its own account id could name someone
    // else's.
    private static final String ORGANIZATION = "X-ELMOS-Organization-ID";
    private static final String ACTOR = "X-ELMOS-Actor-ID";

    private final PlatformAdminPort platform;

    public PlatformAdminController(PlatformAdminPort platform) {
        this.platform = platform;
    }

    public record AdjustRequest(
            String organizationId, String direction, long amountMinor,
            String reason, String idempotencyKey) {}

    public record GrantRequest(String accountId, String platformRole, String reason) {}

    public record RevokeRequest(String accountId, String reason) {}

    @GetMapping("/wallets")
    ResponseEntity<?> wallets(
            @RequestHeader(ORGANIZATION) String organizationId,
            @RequestHeader(ACTOR) String actorId,
            @RequestParam(required = false) String after,
            @RequestParam(defaultValue = "50") int limit
    ) {
        String adminAccountId = resolve(organizationId, actorId);
        if (adminAccountId == null) {
            return refusal(PlatformAdminPort.Decision.DENIED_NOT_ADMIN);
        }
        return relay(platform.wallets(adminAccountId, blankToNull(after), limit));
    }

    @GetMapping("/wallets/{organizationId}/ledger")
    ResponseEntity<?> ledger(
            @RequestHeader(ORGANIZATION) String organizationId,
            @RequestHeader(ACTOR) String actorId,
            @PathVariable("organizationId") String targetOrganizationId,
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset
    ) {
        String adminAccountId = resolve(organizationId, actorId);
        if (adminAccountId == null) {
            return refusal(PlatformAdminPort.Decision.DENIED_NOT_ADMIN);
        }
        // NOTE: organizationId here is the ADMINISTRATOR's own tenant, used only
        // to resolve who they are. The tenant being read is the path variable.
        return relay(platform.ledger(adminAccountId, targetOrganizationId, limit, offset));
    }

    @GetMapping("/topups")
    ResponseEntity<?> topups(
            @RequestHeader(ORGANIZATION) String organizationId,
            @RequestHeader(ACTOR) String actorId,
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "50") int limit
    ) {
        String adminAccountId = resolve(organizationId, actorId);
        if (adminAccountId == null) {
            return refusal(PlatformAdminPort.Decision.DENIED_NOT_ADMIN);
        }
        return relay(platform.topups(adminAccountId, blankToNull(status), limit));
    }

    @GetMapping("/execution-jobs")
    ResponseEntity<?> jobs(
            @RequestHeader(ORGANIZATION) String organizationId,
            @RequestHeader(ACTOR) String actorId,
            @RequestParam(required = false) String status,
            @RequestParam(name = "organizationId", required = false) String targetOrganizationId,
            @RequestParam(defaultValue = "25") int limitPerOrganization
    ) {
        String adminAccountId = resolve(organizationId, actorId);
        if (adminAccountId == null) {
            return refusal(PlatformAdminPort.Decision.DENIED_NOT_ADMIN);
        }
        return relay(platform.jobs(adminAccountId, blankToNull(status),
                blankToNull(targetOrganizationId), limitPerOrganization));
    }

    @PostMapping("/wallets/adjust")
    ResponseEntity<?> adjust(
            @RequestHeader(ORGANIZATION) String organizationId,
            @RequestHeader(ACTOR) String actorId,
            @RequestBody AdjustRequest request
    ) {
        if (request.reason() == null || request.reason().isBlank()) {
            // Also refused by the database. Checked here as well so the console
            // gets a useful message instead of an opaque DENIED_POLICY, not
            // because this check is the one that matters.
            return ResponseEntity.badRequest().body(Map.of(
                    "status", "REJECTED", "code", "ADJUSTMENT_REASON_REQUIRED"));
        }
        String adminAccountId = resolve(organizationId, actorId);
        if (adminAccountId == null) {
            return refusal(PlatformAdminPort.Decision.DENIED_NOT_ADMIN);
        }
        var result = platform.adjust(adminAccountId, request.organizationId(),
                request.direction(), BigDecimal.valueOf(request.amountMinor()),
                request.reason(), request.idempotencyKey());
        if (!result.decision().allowed()) {
            return refusal(result.decision());
        }
        return ResponseEntity.ok(Map.of("status", "ALLOWED", "entryId", result.entryId()));
    }

    @PostMapping("/administrators/grant")
    ResponseEntity<?> grant(
            @RequestHeader(ORGANIZATION) String organizationId,
            @RequestHeader(ACTOR) String actorId,
            @RequestBody GrantRequest request
    ) {
        String adminAccountId = resolve(organizationId, actorId);
        if (adminAccountId == null) {
            return refusal(PlatformAdminPort.Decision.DENIED_NOT_ADMIN);
        }
        var decision = platform.grant(adminAccountId, request.accountId(),
                request.platformRole(), request.reason());
        return decision.allowed()
                ? ResponseEntity.ok(Map.of("status", "ALLOWED"))
                : refusal(decision);
    }

    @PostMapping("/administrators/revoke")
    ResponseEntity<?> revoke(
            @RequestHeader(ORGANIZATION) String organizationId,
            @RequestHeader(ACTOR) String actorId,
            @RequestBody RevokeRequest request
    ) {
        String adminAccountId = resolve(organizationId, actorId);
        if (adminAccountId == null) {
            return refusal(PlatformAdminPort.Decision.DENIED_NOT_ADMIN);
        }
        var decision = platform.revoke(adminAccountId, request.accountId(), request.reason());
        return decision.allowed()
                ? ResponseEntity.ok(Map.of("status", "ALLOWED"))
                : refusal(decision);
    }

    private static ResponseEntity<?> relay(PlatformAdminPort.Page<?> page) {
        if (!page.decision().allowed()) {
            return refusal(page.decision());
        }
        return ResponseEntity.ok(Map.of("status", "ALLOWED", "rows", page.rows()));
    }

    /**
     * Every refusal is a 403 carrying its code, including
     * {@code DENIED_LAST_APPROVER}. That one is arguably a 409 -- the request is
     * well formed and the caller is authorized -- but splitting it out would
     * make the console handle two shapes for the same class of answer, and the
     * code in the body already says exactly what happened.
     */
    private static ResponseEntity<?> refusal(PlatformAdminPort.Decision decision) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(Map.of("status", "DENIED", "code", decision.name()));
    }

    private String resolve(String organizationId, String actorId) {
        return platform.resolveAdminAccount(organizationId, actorId);
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    @Configuration
    static class PlatformAdminConfiguration {
        @Bean
        PlatformAdminPort platformAdminPort(JdbcClient jdbc) {
            return new io.elmos.persistence.JdbcPlatformAdminStore(jdbc);
        }
    }
}
