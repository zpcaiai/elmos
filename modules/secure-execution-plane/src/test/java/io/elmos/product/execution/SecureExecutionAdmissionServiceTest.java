package io.elmos.product.execution;

import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.List;
import static io.elmos.product.execution.SecureExecutionModels.*;
import static org.junit.jupiter.api.Assertions.*;

class SecureExecutionAdmissionServiceTest {
    private final SecureExecutionAdmissionService service = new SecureExecutionAdmissionService();

    @Test void blocksSelfClaimedRunnerPersistedSecretsAndOfflinePrivilegeExpansion() {
        var result = service.evaluate(request(false, true, true));
        assertEquals(Decision.BLOCKED, result.decision());
        assertTrue(result.blockers().contains("RUNNER_SELF_CLAIM_NOT_TRUSTED"));
        assertTrue(result.blockers().contains("SECRET_PERSISTENCE_FORBIDDEN"));
        assertTrue(result.blockers().contains("OFFLINE_PERMIT_CANNOT_CREATE_RIGHTS"));
    }

    @Test void completeContractOnlyReachesExternalExecutionGate() {
        var result = service.evaluate(request(true, false, false));
        assertEquals(Decision.READY_FOR_EXTERNAL_GATE, result.decision());
        assertFalse(result.externalOperationExecuted()); assertFalse(result.exactlyOnceClaimed());
    }

    private static AdmissionRequest request(boolean verified, boolean secretPersisted, boolean expandsRights) {
        return new AdmissionRequest("org", "task", "runner", 7, "a".repeat(64), "b".repeat(64),
                IsolationProvider.GVISOR, Instant.parse("2026-07-22T00:00:00Z"), true, verified, true, true,
                true, true, true, true, true, true, true, true, true, secretPersisted, true, true, true, true,
                true, true, true, expandsRights, true, true, true, true, List.of("evidence://runner/attestation"));
    }
}
