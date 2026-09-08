package io.elmos.liveworkbench;

import io.elmos.product.execution.SecureExecutionModels;

import static io.elmos.liveworkbench.LwContracts.*;
import static io.elmos.liveworkbench.ProductionContracts.*;

/** Host-owned effect boundary. Implementations must be exact, authenticated, idempotent and reconcilable. */
public interface SandboxProviderPort {
    default boolean configured() { return true; }
    /** Bounded operational probe. A configured but unreachable provider is never readiness-UP. */
    default boolean ready() { return configured(); }
    SecureExecutionModels.AdmissionRequest preflight(PrincipalScope scope, String sessionId,
                                                     CreateSessionRequest request, String idempotencyKey);
    ProviderAllocation allocate(PrincipalScope scope, String sessionId, CreateSessionRequest request,
                                String idempotencyKey, long requestedHardDeadlineEpochSecond);
    CleanupOutcome cleanupUnknownAllocation(PrincipalScope scope, String controlSessionId,
                                             String allocationIdempotencyKey, String reason);
    ProviderCommandResult dispatchDebug(PrincipalScope scope, SessionView session, String commandId,
                                        String idempotencyKey, DebugRequest request);
    ProviderCommandResult reconcileDebug(PrincipalScope scope, SessionView session, String commandId,
                                         String idempotencyKey);
    CleanupOutcome cleanup(PrincipalScope scope, SessionView session, String reason);
    PreviewAccess previewAccess(PrincipalScope scope, SessionView session);
    SourceContent readSource(PrincipalScope scope, SourceAnchor anchor);
    MissionAttemptReceipt assess(PrincipalScope scope, LearningMission mission, MissionAttemptRequest request,
                                 String attemptId, String idempotencyKey);
    MissionAttemptReceipt reconcileAssessment(PrincipalScope scope, LearningMission mission,
                                              String attemptId, String idempotencyKey);
}
