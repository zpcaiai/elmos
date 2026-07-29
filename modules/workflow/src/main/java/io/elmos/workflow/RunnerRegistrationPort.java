package io.elmos.workflow;

import java.time.Instant;
import java.util.List;

/**
 * Authentication and lifecycle boundary for hosted runners.
 *
 * <p>Enrollment credentials are short-lived, revocable and bound to one pool.
 * Self-declared sandbox facts are recorded during registration but never make a
 * node schedulable; {@link #verifyAttestation} is a separate operator action.</p>
 */
public interface RunnerRegistrationPort {
    record EnrollmentCredential(
            String credentialId,
            String poolId,
            String token,
            Instant expiresAt) {
    }

    record NodeCredential(String runnerNodeId, Instant expiresAt) {
    }

    final class RunnerAuthenticationException extends RuntimeException {
        private final String code;

        public RunnerAuthenticationException(String code) {
            super(code);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    NodeCredential register(
            String runnerNodeId,
            String poolId,
            String agentVersion,
            List<String> capabilities,
            int maxConcurrency,
            String enrollmentToken,
            String nodeTokenSha256,
            boolean rootlessDeclared,
            boolean readOnlyRootDeclared,
            boolean capabilitiesDroppedDeclared,
            boolean networkDefaultDenyDeclared,
            String imageAllowlistVersion
    );

    /** Reconnects a previously enrolled node using its durable node credential. */
    NodeCredential resume(String runnerNodeId, String nodeToken);

    EnrollmentCredential issueEnrollment(
            String organizationId,
            String poolId,
            String actorId,
            int ttlSeconds);

    void revokeEnrollment(
            String organizationId,
            String credentialId,
            String actorId);

    Instant rotateNodeCredential(
            String runnerNodeId,
            String presentedNodeToken,
            String nextTokenSha256,
            String rotationRequestId);

    boolean heartbeat(String runnerNodeId, String nodeToken);

    void authorizeNode(String runnerNodeId, String nodeToken);

    void verifyAttestation(String runnerNodeId, String verifierActorId);

    void requestDrain(String runnerNodeId, String actorId);
}
