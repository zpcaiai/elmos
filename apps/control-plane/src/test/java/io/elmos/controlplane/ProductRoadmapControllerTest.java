package io.elmos.controlplane;

import io.elmos.roadmap.ProductRoadmapModels.EvaluationRequest;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static io.elmos.roadmap.ProductRoadmapModels.Decision.BLOCKED;
import static org.junit.jupiter.api.Assertions.*;

class ProductRoadmapControllerTest {
    @Test void exposesEightBatchesAndDoesNotAutoApproveEmptyEvidence() {
        var controller = new ProductRoadmapController();
        assertEquals(8, controller.capabilities().size());
        var request = new EvaluationRequest(27, "org", "run", "a".repeat(64), "p1", "human", Instant.now(), List.of());
        var result = controller.evaluate(27, request);
        assertEquals(BLOCKED, result.decision());
        assertFalse(result.humanApprovalGranted());
        assertFalse(result.externalOperationExecuted());
    }
}
