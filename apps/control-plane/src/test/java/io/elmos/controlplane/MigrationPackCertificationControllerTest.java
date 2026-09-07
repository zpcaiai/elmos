package io.elmos.controlplane;

import io.elmos.migrationpack.MigrationPackModels.AdmissionRequest;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static io.elmos.migrationpack.MigrationPackModels.AdmissionDecision.BLOCKED;
import static org.junit.jupiter.api.Assertions.*;

class MigrationPackCertificationControllerTest {
    @Test void exposesM29ThroughM34ButNeverCertifiesMissingEvidence() {
        var controller = new MigrationPackCertificationController();
        assertEquals(6, controller.capabilities().size());
        var request = new AdmissionRequest(29, "org", "assessment", "a".repeat(64), "b".repeat(64),
                "v1", "human", Instant.now(), List.of());
        var result = controller.evaluate(29, request);
        assertEquals(BLOCKED, result.decision());
        assertFalse(result.certified());
        assertEquals("scripts/batch29/run_route_gate.py", result.soleCertificationAuthority());
    }
}
