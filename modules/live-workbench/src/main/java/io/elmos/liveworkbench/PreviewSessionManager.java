package io.elmos.liveworkbench;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

import static io.elmos.liveworkbench.LwContracts.*;

/** Fixed-wall-clock preview lifecycle. It deliberately has no renewal operation. */
public final class PreviewSessionManager {
    public interface CleanupPort { CleanupReceipt terminateAndObserve(PreviewSession session, String reason, long now); }
    private final Map<String, PreviewSession> sessions = new HashMap<>();
    private final Map<String, Integer> slotsByAccount = new HashMap<>();
    private final CleanupPort cleanupPort;

    public PreviewSessionManager(CleanupPort cleanupPort) { this.cleanupPort = Objects.requireNonNull(cleanupPort); }

    public synchronized PreviewSession create(Authority authority, long now, long providerHardDeadline, int slotWeight) {
        if (!authority.validAt(now, Capability.HOST_EXEC)) throw new SecurityException("host-exec authority required");
        if (slotWeight < 1) throw new IllegalArgumentException("slotWeight");
        int inUse = slotsByAccount.getOrDefault(authority.accountId(), 0);
        if (inUse + slotWeight > MAX_ACCOUNT_SLOTS) throw new IllegalStateException("execution slot quota exceeded");
        if (providerHardDeadline < now + PREVIEW_SECONDS + CLEANUP_SECONDS) throw new IllegalStateException("provider lifetime cannot cover preview and cleanup");
        Binding binding = authority.binding();
        if (sessions.containsKey(binding.sessionId())) throw new IllegalStateException("session id already exists");
        PreviewSession session = new PreviewSession(binding, SessionState.PREPARING, RuntimeStatus.PENDING, now, null, null,
                PREVIEW_SECONDS, CLEANUP_SECONDS, providerHardDeadline, slotWeight, null, false);
        sessions.put(binding.sessionId(), session); slotsByAccount.put(authority.accountId(), inUse + slotWeight);
        return session;
    }

    public synchronized PreviewSession commitReady(Authority authority, ReadinessAttestation attestation, long now) {
        PreviewSession session = required(authority.binding().sessionId());
        requireSame(authority, session, now, Capability.HOST_EXEC);
        if (session.state() != SessionState.PREPARING) throw new IllegalStateException("ready may only commit once from preparing");
        if (!session.binding().equals(attestation.binding()) || now != attestation.verifiedAt()) throw new IllegalArgumentException("attestation binding/time mismatch");
        if (session.providerHardDeadline() < now + PREVIEW_SECONDS + CLEANUP_SECONDS) throw new IllegalStateException("provider capacity changed before readiness");
        PreviewSession ready = new PreviewSession(session.binding(), SessionState.READY, RuntimeStatus.RUNNING, session.createdAt(), now,
                now + PREVIEW_SECONDS, PREVIEW_SECONDS, CLEANUP_SECONDS, session.providerHardDeadline(), session.slotWeight(), attestation.id(), false);
        sessions.put(ready.binding().sessionId(), ready); return ready;
    }

    public synchronized PreviewSession get(Authority authority, String sessionId, long now) {
        PreviewSession session = required(sessionId); requireSame(authority, session, now, Capability.INSPECT); return session;
    }

    public synchronized CleanupReceipt expireOrTerminate(Authority authority, String sessionId, String reason, long now) {
        PreviewSession session = required(sessionId); requireSame(authority, session, now, Capability.HOST_EXEC);
        if (session.state() == SessionState.CLEANED || session.state() == SessionState.QUARANTINED) throw new IllegalStateException("session already cleaned");
        if (session.state() == SessionState.READY && now < session.expiresAt() && !"explicit-user-stop".equals(reason) && !"security-violation".equals(reason))
            throw new IllegalStateException("fixed preview window is still active");
        CleanupReceipt receipt = cleanupPort.terminateAndObserve(session, reason, now);
        if (!receipt.binding().equals(session.binding())) throw new IllegalStateException("cleanup receipt binding mismatch");
        sessions.put(sessionId, new PreviewSession(session.binding(), receipt.status(), RuntimeStatus.STOPPED, session.createdAt(), session.firstReadyAt(),
                session.expiresAt(), PREVIEW_SECONDS, CLEANUP_SECONDS, session.providerHardDeadline(), session.slotWeight(), session.readinessId(), false));
        slotsByAccount.compute(authority.accountId(), (key, used) -> Math.max(0, (used == null ? 0 : used) - session.slotWeight()));
        return receipt;
    }

    private PreviewSession required(String sessionId) { PreviewSession result = sessions.get(sessionId); if (result == null) throw new IllegalArgumentException("unknown session"); return result; }
    private static void requireSame(Authority authority, PreviewSession session, long now, Capability capability) {
        if (authority == null || !authority.validAt(now, capability) || !authority.binding().equals(session.binding())) throw new SecurityException("session authority denied");
    }
}
