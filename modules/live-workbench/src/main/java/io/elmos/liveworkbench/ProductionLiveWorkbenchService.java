package io.elmos.liveworkbench;

import io.elmos.product.execution.SecureExecutionAdmissionService;
import io.elmos.product.execution.SecureExecutionModels;

import java.time.Clock;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import static io.elmos.liveworkbench.LwContracts.*;
import static io.elmos.liveworkbench.ProductionContracts.*;

/**
 * Durable production orchestration. All external effects cross the typed provider port;
 * retries reconcile unknown outcomes instead of replaying side effects.
 */
public final class ProductionLiveWorkbenchService {
    private static final long PREPARATION_BUDGET_SECONDS = 300;

    private final LiveWorkbenchStore store;
    private final LiveWorkbenchCatalogStore catalog;
    private final SandboxProviderPort provider;
    private final SecureExecutionAdmissionService admission;
    private final Clock clock;

    public ProductionLiveWorkbenchService(LiveWorkbenchStore store, LiveWorkbenchCatalogStore catalog, SandboxProviderPort provider,
                                          SecureExecutionAdmissionService admission, Clock clock) {
        this.store = java.util.Objects.requireNonNull(store);
        this.catalog = java.util.Objects.requireNonNull(catalog);
        this.provider = java.util.Objects.requireNonNull(provider);
        this.admission = java.util.Objects.requireNonNull(admission);
        this.clock = java.util.Objects.requireNonNull(clock);
    }

    public ApiSession create(PrincipalScope scope, CreateSessionRequest request, String idempotencyKey) {
        requireAuthority(scope, "workbench.session.create");
        validIdempotencyKey(idempotencyKey);
        long now = now();
        validateDelivery(scope, request);
        String requestDigest = requestDigest(request);
        LiveWorkbenchStore.Reservation reservation = store.reserve(scope, request, UUID.randomUUID().toString(),
                idempotencyKey, requestDigest, now);
        if (!reservation.created()) return api(reservation.session(), now);

        SessionView reserved = reservation.session();
        ProviderAllocation allocation = null;
        boolean allocationAttempted = false;
        try {
            SecureExecutionModels.AdmissionRequest admissionRequest = provider.preflight(scope, reserved.sessionId(), request,
                    "admission-" + idempotencyKey);
            SecureExecutionModels.AdmissionResult result = admission.evaluate(admissionRequest);
            if (result.decision() != SecureExecutionModels.Decision.READY_FOR_EXTERNAL_GATE) {
                String code = result.blockers().isEmpty() ? "SANDBOX_ADMISSION_BLOCKED" : result.blockers().getFirst();
                store.failPreparation(scope.tenantId(), reserved.sessionId(), reserved.version(), code, now);
                throw LiveWorkbenchException.denied(code);
            }
            long requestedDeadline = Math.addExact(now, PREPARATION_BUDGET_SECONDS + PREVIEW_SECONDS + CLEANUP_SECONDS);
            allocationAttempted = true;
            allocation = provider.allocate(scope, reserved.sessionId(), request, idempotencyKey, requestedDeadline);
            if (allocation.hardDeadlineEpochSecond() < requestedDeadline)
                throw LiveWorkbenchException.unavailable("PROVIDER_HARD_DEADLINE_TOO_SHORT");
            SessionView bound = store.bindProvider(scope.tenantId(), reserved.sessionId(), reserved.version(), allocation);
            store.recordAudit(scope.tenantId(), scope.actorId(), bound.sessionId(), "SANDBOX_ALLOCATED", "PREPARING",
                    LwDigest.sha256(allocation.providerSessionId() + "\n" + allocation.resourceLeaseId()), now);
            return api(bound, now);
        } catch (LiveWorkbenchException error) {
            compensateAllocation(scope, reserved, allocation, allocationAttempted, idempotencyKey, now);
            failIfStillPreparing(scope.tenantId(), reserved.sessionId(), error.code(), now);
            throw error;
        } catch (RuntimeException error) {
            compensateAllocation(scope, reserved, allocation, allocationAttempted, idempotencyKey, now);
            failIfStillPreparing(scope.tenantId(), reserved.sessionId(), "SANDBOX_PREPARATION_FAILED", now);
            throw LiveWorkbenchException.unavailable("SANDBOX_PREPARATION_FAILED");
        }
    }

    /** Called only by an authenticated runtime/verifier callback after smoke and capacity checks commit. */
    public ApiSession markReady(PrincipalScope scope, String sessionId, long expectedVersion, ReadinessRequest readiness) {
        requireAuthority(scope, "workbench.runtime.commit");
        SessionView current = scoped(scope, sessionId, false);
        long now = now();
        if (readiness.verifiedAtEpochSecond() < current.createdAtEpochSecond()
                || Math.abs(readiness.verifiedAtEpochSecond() - now) > 60)
            throw LiveWorkbenchException.conflict("READINESS_TIMESTAMP_INVALID");
        SessionView ready = store.commitReady(scope.tenantId(), sessionId, expectedVersion, readiness);
        return api(ready, now);
    }

    public ApiSession status(PrincipalScope scope, String sessionId) {
        requireAuthority(scope, "workbench.session.read");
        return api(scoped(scope, sessionId, true), now());
    }

    public PreviewAccess previewAccess(PrincipalScope scope, String sessionId) {
        requireAuthority(scope, "workbench.session.read");
        SessionView session = scoped(scope, sessionId, true);
        long now = now();
        if (session.state() != SessionState.READY || session.expiresAtEpochSecond() == null || now >= session.expiresAtEpochSecond())
            throw LiveWorkbenchException.conflict("PREVIEW_SESSION_EXPIRED_OR_NOT_READY");
        PreviewAccess access = provider.previewAccess(scope, session);
        if (access.expiresAtEpochSecond() > session.expiresAtEpochSecond() || access.expiresAtEpochSecond() <= now)
            throw LiveWorkbenchException.conflict("PREVIEW_ACCESS_EXPIRY_INVALID");
        if (!access.audience().equals(scope.actorId()) && !access.audience().equals(scope.accountId()))
            throw LiveWorkbenchException.denied("PREVIEW_ACCESS_AUDIENCE_MISMATCH");
        return access;
    }

    public DebugReceipt debug(PrincipalScope scope, String sessionId, int generation,
                              DebugRequest request, String idempotencyKey) {
        requireAuthority(scope, request.sideEffecting() ? "workbench.debug.control" : "workbench.debug.inspect");
        validIdempotencyKey(idempotencyKey);
        SessionView session = scoped(scope, sessionId, true);
        long now = now();
        String requestDigest = LwDigest.sha256(request.command() + "\n" + request.argumentsDigest() + "\n"
                + request.stopEpoch() + "\n" + request.controlLeaseId());
        LiveWorkbenchStore.CommandReservation reservation = store.reserveCommand(scope.tenantId(), sessionId, generation,
                request, UUID.randomUUID().toString(), idempotencyKey, requestDigest, now);
        DebugReceipt receipt = reservation.receipt();
        if (receipt.state() == CommandState.COMMITTED || receipt.state() == CommandState.DENIED) return receipt;

        ProviderCommandResult providerResult = reservation.created()
                ? provider.dispatchDebug(scope, session, receipt.commandId(), idempotencyKey, request)
                : provider.reconcileDebug(scope, session, receipt.commandId(), idempotencyKey);
        String code = switch (providerResult.state()) {
            case COMMITTED -> "PROVIDER_COMMITTED";
            case DENIED -> "PROVIDER_DENIED";
            case UNKNOWN -> "RECONCILIATION_REQUIRED";
            default -> throw new IllegalStateException("unexpected provider result");
        };
        return store.completeCommand(scope.tenantId(), sessionId, idempotencyKey,
                new LiveWorkbenchStore.CommandStateUpdate(providerResult.state(), code,
                        providerResult.evidenceRef(), providerResult.responseDigest()), now);
    }

    public EventView appendRuntimeEvent(PrincipalScope scope, String sessionId, RuntimeEventRequest event) {
        requireAuthority(scope, "workbench.runtime.event");
        SessionView session = scoped(scope, sessionId, false);
        long now = now();
        if (session.state() != SessionState.READY || session.firstReadyAtEpochSecond() == null
                || session.expiresAtEpochSecond() == null || now >= session.expiresAtEpochSecond())
            throw LiveWorkbenchException.conflict("EVENT_SESSION_EXPIRED_OR_NOT_READY");
        if (event.serverTimeEpochSecond() < session.firstReadyAtEpochSecond()
                || event.serverTimeEpochSecond() > Math.min(session.expiresAtEpochSecond(), now + 60))
            throw LiveWorkbenchException.conflict("EVENT_TIMESTAMP_INVALID");
        return store.appendEvent(scope.tenantId(), sessionId, event);
    }

    public List<EventView> events(PrincipalScope scope, String sessionId, long afterSequence, int limit) {
        requireAuthority(scope, "workbench.session.read");
        if (afterSequence < 0 || limit < 1 || limit > 500) throw new IllegalArgumentException("event cursor or limit");
        scoped(scope, sessionId, true);
        return store.events(scope.tenantId(), sessionId, afterSequence, limit);
    }

    public ApiSession terminate(PrincipalScope scope, String sessionId, long expectedVersion, String reason) {
        requireAuthority(scope, "workbench.session.terminate");
        if (reason == null || reason.isBlank() || reason.length() > 200) throw new IllegalArgumentException("cleanup reason");
        SessionView current = scoped(scope, sessionId, true);
        SessionView pending = store.requestCleanup(scope.tenantId(), sessionId, expectedVersion, reason, now());
        if (pending.state() == SessionState.CLEANED || pending.state() == SessionState.QUARANTINED) return api(pending, now());
        return api(cleanup(scope, pending, reason), now());
    }

    /** Claims bounded work with SKIP LOCKED; safe for multiple reaper replicas. */
    public int sweepExpired(int limit) {
        if (limit < 1 || limit > 500) throw new IllegalArgumentException("reaper limit");
        List<SessionView> sessions = store.claimExpired(now(), limit);
        for (SessionView session : sessions) {
            PrincipalScope scope = new PrincipalScope(session.tenantId(), session.accountId(), session.actorId(),
                    "system-reaper", Set.of("workbench.session.terminate"));
            try { cleanup(scope, session, "deadline"); }
            catch (LiveWorkbenchException ignored) { /* durable CLEANUP_PENDING state is retried by the next sweep */ }
        }
        return sessions.size();
    }

    private SessionView cleanup(PrincipalScope scope, SessionView pending, String reason) {
        try {
            CleanupOutcome outcome;
            if (pending.providerSessionId() == null) {
                outcome = new CleanupOutcome(SessionState.CLEANED, java.util.Map.of("providerAllocationNeverCommitted", true),
                        "control-plane", List.of("control-plane:no-provider-allocation"), now());
            } else {
                outcome = provider.cleanup(scope, pending, reason);
            }
            validateCleanupOutcome(pending, outcome);
            return store.completeCleanup(scope.tenantId(), pending.sessionId(), pending.version(), outcome);
        } catch (LiveWorkbenchException error) {
            store.recordAudit(scope.tenantId(), scope.actorId(), pending.sessionId(), "CLEANUP_DEFERRED", error.code(),
                    LwDigest.sha256(error.code()), now());
            throw error;
        }
    }

    private void validateCleanupOutcome(SessionView pending, CleanupOutcome outcome) {
        long now = now();
        if (outcome.observedAtEpochSecond() < pending.createdAtEpochSecond() || outcome.observedAtEpochSecond() > now + 60)
            throw LiveWorkbenchException.unavailable("CLEANUP_OBSERVATION_TIMESTAMP_INVALID");
        if (pending.resourceMembers().isEmpty()) {
            if (!outcome.memberChecks().equals(java.util.Map.of("providerAllocationNeverCommitted", true)))
                throw LiveWorkbenchException.unavailable("CLEANUP_RESOURCE_COVERAGE_INVALID");
        } else if (!outcome.memberChecks().keySet().equals(pending.resourceMembers().keySet())) {
            throw LiveWorkbenchException.unavailable("CLEANUP_RESOURCE_COVERAGE_INVALID");
        }
    }

    private SessionView scoped(PrincipalScope scope, String sessionId, boolean accountBound) {
        SessionView session = store.find(scope.tenantId(), sessionId).orElseThrow(LiveWorkbenchException::notFound);
        if (accountBound && !session.accountId().equals(scope.accountId()) && !scope.has("workbench.admin"))
            throw LiveWorkbenchException.notFound();
        return session;
    }

    private void failIfStillPreparing(String tenantId, String sessionId, String code, long now) {
        store.find(tenantId, sessionId).filter(session -> session.state() == SessionState.PREPARING).ifPresent(session -> {
            try { store.failPreparation(tenantId, sessionId, session.version(), code, now); }
            catch (LiveWorkbenchException ignored) { /* another actor won the state transition */ }
        });
    }

    private void compensateAllocation(PrincipalScope scope, SessionView reserved, ProviderAllocation allocation,
                                      boolean allocationAttempted, String allocationIdempotencyKey, long now) {
        if (!allocationAttempted) return;
        try {
            CleanupOutcome outcome;
            if (allocation == null) {
                outcome = provider.cleanupUnknownAllocation(scope, reserved.sessionId(), allocationIdempotencyKey,
                        "allocation-outcome-unknown");
            } else {
                SessionView provisional = new SessionView(reserved.tenantId(), reserved.accountId(), reserved.actorId(), reserved.sessionId(),
                        reserved.deliveryId(), reserved.repositoryId(), reserved.snapshotId(), reserved.runtimeProfileId(), reserved.scenario(),
                        reserved.mode(), reserved.generation(), reserved.slotWeight(), reserved.state(), reserved.runtimeStatus(),
                        reserved.createdAtEpochSecond(), reserved.firstReadyAtEpochSecond(), reserved.expiresAtEpochSecond(),
                        allocation.hardDeadlineEpochSecond(), allocation.providerSessionId(), allocation.resourceLeaseId(),
                        allocation.members(), allocation.evidenceRefs(), reserved.version());
                outcome = provider.cleanup(scope, provisional, "allocation-compensation");
            }
            store.recordAudit(scope.tenantId(), scope.actorId(), reserved.sessionId(), "ALLOCATION_COMPENSATED",
                    outcome.status().name(), LwDigest.sha256(outcome.status().name()), now);
        } catch (RuntimeException cleanupFailure) {
            store.recordAudit(scope.tenantId(), scope.actorId(), reserved.sessionId(), "ALLOCATION_COMPENSATION_UNKNOWN",
                    "QUARANTINE_REQUIRED", LwDigest.sha256("QUARANTINE_REQUIRED"), now);
        }
    }

    private ApiSession api(SessionView session, long now) {
        return new ApiSession(session, now, session.remainingSeconds(now), VERSION);
    }

    private static String requestDigest(CreateSessionRequest request) {
        return LwDigest.sha256(request.deliveryId() + "\n" + request.repositoryId() + "\n" + request.snapshotId() + "\n"
                + request.runtimeProfileId() + "\n" + request.scenario() + "\n" + request.mode() + "\n"
                + request.slotWeight() + "\n" + request.debugRequired());
    }

    private void validateDelivery(PrincipalScope scope, CreateSessionRequest request) {
        LiveWorkbenchService.ArtifactDelivery delivery = catalog.delivery(scope.tenantId(), request.deliveryId())
                .orElseThrow(() -> LiveWorkbenchException.conflict("DELIVERY_NOT_REGISTERED"));
        if (!delivery.repositoryId().equals(request.repositoryId()) || !delivery.snapshotId().equals(request.snapshotId())
                || !delivery.runtimeProfileId().equals(request.runtimeProfileId()))
            throw LiveWorkbenchException.conflict("DELIVERY_BINDING_MISMATCH");
        requireAvailable(delivery, "preview");
        if (request.debugRequired()) requireAvailable(delivery, "debug");
        if ("compare".equals(request.mode())) requireAvailable(delivery, "compare");
        RuntimeProfile profile = catalog.profile(scope.tenantId(), request.runtimeProfileId())
                .orElseThrow(() -> LiveWorkbenchException.conflict("RUNTIME_PROFILE_NOT_REGISTERED"));
        if (profile.qualification() != Qualification.QUALIFIED)
            throw LiveWorkbenchException.conflict("RUNTIME_PROFILE_NOT_QUALIFIED");
    }

    private static void requireAvailable(LiveWorkbenchService.ArtifactDelivery delivery, String capability) {
        LiveWorkbenchService.CapabilityStatus status = delivery.capabilities().get(capability);
        if (status == null || status.status() != SkillStatus.AVAILABLE)
            throw LiveWorkbenchException.conflict("DELIVERY_CAPABILITY_NOT_AVAILABLE");
    }

    private static void validIdempotencyKey(String value) {
        if (value == null || !value.matches("[A-Za-z0-9._:-]{8,200}"))
            throw new IllegalArgumentException("valid Idempotency-Key required");
    }

    private static void requireAuthority(PrincipalScope scope, String authority) {
        if (!scope.has(authority)) throw LiveWorkbenchException.denied("AUTHORITY_REQUIRED");
    }

    private long now() { return clock.instant().getEpochSecond(); }
}
