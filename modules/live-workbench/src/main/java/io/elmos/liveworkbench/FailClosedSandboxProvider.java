package io.elmos.liveworkbench;

import io.elmos.product.execution.SecureExecutionModels;

import static io.elmos.liveworkbench.ProductionContracts.*;

/** Default production behavior when no qualified provider is configured. */
public final class FailClosedSandboxProvider implements SandboxProviderPort {
    @Override public boolean configured() { return false; }
    @Override public boolean ready() { return false; }
    private LiveWorkbenchException missing() { return LiveWorkbenchException.unavailable("QUALIFIED_SANDBOX_PROVIDER_NOT_CONFIGURED"); }
    @Override public SecureExecutionModels.AdmissionRequest preflight(PrincipalScope scope, String sessionId, CreateSessionRequest request, String idempotencyKey) { throw missing(); }
    @Override public ProviderAllocation allocate(PrincipalScope scope, String sessionId, CreateSessionRequest request, String idempotencyKey, long deadline) { throw missing(); }
    @Override public CleanupOutcome cleanupUnknownAllocation(PrincipalScope scope, String controlSessionId, String allocationIdempotencyKey, String reason) { throw missing(); }
    @Override public ProviderCommandResult dispatchDebug(PrincipalScope scope, SessionView session, String commandId, String idempotencyKey, DebugRequest request) { throw missing(); }
    @Override public ProviderCommandResult reconcileDebug(PrincipalScope scope, SessionView session, String commandId, String idempotencyKey) { throw missing(); }
    @Override public CleanupOutcome cleanup(PrincipalScope scope, SessionView session, String reason) { throw missing(); }
    @Override public PreviewAccess previewAccess(PrincipalScope scope, SessionView session) { throw missing(); }
    @Override public SourceContent readSource(PrincipalScope scope, io.elmos.liveworkbench.LwContracts.SourceAnchor anchor) { throw missing(); }
    @Override public MissionAttemptReceipt assess(PrincipalScope scope, io.elmos.liveworkbench.LwContracts.LearningMission mission, MissionAttemptRequest request, String attemptId, String idempotencyKey) { throw missing(); }
    @Override public MissionAttemptReceipt reconcileAssessment(PrincipalScope scope, io.elmos.liveworkbench.LwContracts.LearningMission mission, String attemptId, String idempotencyKey) { throw missing(); }
}
