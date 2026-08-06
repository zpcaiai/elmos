package io.elmos.controlplane;

import io.elmos.commercial.SelfServiceBillingPort;
import io.elmos.commercial.SelfServiceBillingPort.QuotaAdministrationView;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.util.Map;
import java.util.Objects;

/**
 * Operator review and adjustment of a tenant's allowance.
 *
 * <p>Deliberately a separate controller from {@code OperationsObservabilityController}
 * rather than two more methods on it. A quota is not an observation: reading one
 * is a look at a commercial entitlement, and writing one changes what a paying
 * tenant is permitted to do. Keeping them apart means the read path of the
 * console cannot accidentally acquire a write to billing state through a shared
 * helper, and it keeps this file small enough that its two endpoints can be read
 * in full before signing off on them.
 *
 * <p>Authorization is delegated to {@link OperationsAuthorization}, the same
 * component the observability endpoints use. That component exists precisely so
 * this controller did not have to copy the credential and role logic; a second
 * copy would drift, and the copy that drifts is always the one guarding the
 * endpoint nobody re-reads.
 *
 * <p>The two endpoints are split by required role, not by convenience:
 * {@code VIEWER} may read the allowance, and only {@code APPROVER} may change
 * it. Raising a limit costs money and lowering one can stop a tenant's work
 * mid-flight, so it sits at the same level as approving a remediation.
 */
@RestController
@RequestMapping("/api/v1/tenant-quota")
public final class TenantQuotaController {

    /**
     * A constrained token, never free text.
     *
     * <p>The reason flows onto the append-only subscription event log and from
     * there into the audit CSV export. Free text in a CSV field is a delimiter
     * injection waiting to happen and, worse, an audit trail whose values cannot
     * be grouped or counted. An enumerable token keeps the record answerable to
     * "how often did we raise a limit for this reason".
     */
    private static final String REASON_CODE = "[A-Z][A-Z0-9_]{2,47}";

    /**
     * A limit is a monetary-scale quantity, not an arbitrary number. The ceiling
     * is high enough that no legitimate plan reaches it and low enough that a
     * mistyped value cannot silently become an unbounded allowance.
     */
    private static final BigDecimal MAX_LIMIT = new BigDecimal("1000000000");

    private final SelfServiceBillingPort billing;
    private final OperationsAuthorization authorization;

    public TenantQuotaController(SelfServiceBillingPort billing, OperationsAuthorization authorization) {
        this.billing = Objects.requireNonNull(billing, "billing");
        this.authorization = Objects.requireNonNull(authorization, "authorization");
    }

    /**
     * The body of an adjustment.
     *
     * <p>{@code expectedVersion} is required rather than optional. Without it an
     * operator who is looking at a stale screen would overwrite a change made a
     * moment earlier by someone else, and neither of them would find out. With
     * it, the second write is refused and the operator is told to look again.
     */
    public record AdjustmentBody(
            String quotaAllocationId,
            BigDecimal tokenLimit,
            BigDecimal creditLimit,
            long expectedVersion,
            String reasonCode
    ) {}

    @GetMapping
    public QuotaAdministrationView quota(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role
    ) {
        authorization.requireManagement(presentedKey, organizationId, actorId, role, "VIEWER");
        return billing.quotaForAdministration(organizationId);
    }

    /**
     * Changes the allowance and returns the state after the change.
     *
     * <p>Returning the new view rather than an acknowledgement means the caller
     * ends up holding the new version, so the next adjustment starts from a
     * fresh one instead of a number the operator had to copy by hand.
     */
    @PostMapping("/adjust")
    public QuotaAdministrationView adjust(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @RequestBody AdjustmentBody body
    ) {
        authorization.requireManagement(presentedKey, organizationId, actorId, role, "APPROVER");
        requireIdentifier(body.quotaAllocationId(), "quotaAllocationId");
        requireLimit(body.tokenLimit(), "tokenLimit");
        requireLimit(body.creditLimit(), "creditLimit");
        if (body.expectedVersion() < 0) {
            throw new IllegalArgumentException("expectedVersion must not be negative");
        }
        if (body.reasonCode() == null || !body.reasonCode().matches(REASON_CODE)) {
            throw new IllegalArgumentException("reasonCode must be an upper-case token");
        }
        return billing.adjustQuota(
                organizationId,
                actorId,
                body.quotaAllocationId(),
                body.tokenLimit(),
                body.creditLimit(),
                body.expectedVersion(),
                body.reasonCode());
    }

    private static void requireIdentifier(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
        if (!value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            throw new IllegalArgumentException(field + " is not a well-formed identifier");
        }
    }

    /**
     * A negative limit is nonsense and an unbounded one is a mistake nobody
     * notices until the invoice. Both are refused here rather than left to the
     * database, so the operator gets a message naming the field instead of a
     * constraint violation.
     */
    private static void requireLimit(BigDecimal value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " is required");
        }
        if (value.signum() < 0) {
            throw new IllegalArgumentException(field + " must not be negative");
        }
        if (value.compareTo(MAX_LIMIT) > 0) {
            throw new IllegalArgumentException(field + " exceeds the maximum allowance");
        }
    }

    @ExceptionHandler(SecurityException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    Map<String, Object> forbidden() {
        return Map.of("errorCode", "TENANT_QUOTA_FORBIDDEN",
                "message", "Tenant quota authorization failed.", "retryable", false);
    }

    @ExceptionHandler(ObservabilityUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    Map<String, Object> unavailable() {
        return Map.of("errorCode", "TENANT_QUOTA_NOT_CONFIGURED",
                "message", "Tenant quota administration is not configured.", "retryable", false);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> invalid() {
        return Map.of("errorCode", "TENANT_QUOTA_REQUEST_INVALID",
                "message", "The quota request was rejected by its contract.", "retryable", false);
    }

    /**
     * A version mismatch and a floor violation are both conflicts: the request
     * was well-formed, and the current state is what refused it. Retryable is
     * false because the same body will be refused again -- the operator has to
     * re-read the allowance first.
     */
    @ExceptionHandler(SelfServiceBillingPort.BillingStateException.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    Map<String, Object> conflict(SelfServiceBillingPort.BillingStateException error) {
        return Map.of("errorCode", error.code(),
                "message", "The quota changed or the requested limit is below what is already committed.",
                "retryable", false);
    }
}
