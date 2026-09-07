package io.elmos.liveworkbench;

import java.util.List;
import java.util.Optional;

import static io.elmos.liveworkbench.ProductionContracts.*;

/** Durable tenant-scoped state. Implementations must provide transaction and fencing semantics. */
public interface LiveWorkbenchStore {
    record Reservation(SessionView session, boolean created) {}

    Reservation reserve(PrincipalScope scope, CreateSessionRequest request, String sessionId,
                        String idempotencyKey, String requestDigest, long now);
    SessionView bindProvider(String tenantId, String sessionId, long expectedVersion, ProviderAllocation allocation);
    SessionView failPreparation(String tenantId, String sessionId, long expectedVersion, String failureCode, long now);
    Optional<SessionView> find(String tenantId, String sessionId);
    SessionView commitReady(String tenantId, String sessionId, long expectedVersion, ReadinessRequest readiness);
    SessionView requestCleanup(String tenantId, String sessionId, long expectedVersion, String reason, long now);
    List<SessionView> claimExpired(long now, int limit);
    SessionView completeCleanup(String tenantId, String sessionId, long expectedVersion, CleanupOutcome outcome);

    record CommandReservation(DebugReceipt receipt, boolean created) {}
    CommandReservation reserveCommand(String tenantId, String sessionId, int generation, DebugRequest request,
                                      String commandId, String idempotencyKey, String requestDigest, long now);
    DebugReceipt completeCommand(String tenantId, String sessionId, String idempotencyKey,
                                 CommandStateUpdate update, long now);
    record CommandStateUpdate(io.elmos.liveworkbench.LwContracts.CommandState state, String code,
                              String evidenceRef, String responseDigest) {}

    EventView appendEvent(String tenantId, String sessionId, RuntimeEventRequest request);
    List<EventView> events(String tenantId, String sessionId, long afterSequence, int limit);
    void recordAudit(String tenantId, String actorId, String sessionId, String action,
                     String outcome, String payloadDigest, long now);
}
