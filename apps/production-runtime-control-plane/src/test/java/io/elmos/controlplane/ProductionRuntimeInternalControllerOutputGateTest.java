package io.elmos.controlplane;

import io.elmos.productionruntime.ProductionRuntimeCoordinator;
import io.elmos.productionruntime.ProductionRuntimeException;
import io.elmos.productionruntime.ProductionRuntimeModels.AttemptStatus;
import io.elmos.productionruntime.ProductionRuntimeModels.Completion;
import io.elmos.productionruntime.ProductionRuntimeModels.OutputVerificationReceipt;
import io.elmos.productionruntime.ProductionRuntimeStore;
import org.junit.jupiter.api.Test;

import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class ProductionRuntimeInternalControllerOutputGateTest {
    private final ProductionRuntimeInternalAuthenticator authenticator =
            mock(ProductionRuntimeInternalAuthenticator.class);
    private final ProductionRuntimeStore runtime = mock(ProductionRuntimeStore.class);
    private final ProductionRuntimeCoordinator coordinator =
            mock(ProductionRuntimeCoordinator.class);
    private final ProductionRuntimeInternalController controller =
            new ProductionRuntimeInternalController(
                    authenticator, runtime, coordinator);

    @Test
    void bareSuccessfulWorkerCompletionFailsClosed() {
        Completion completion = completion(AttemptStatus.SUCCEEDED);

        ProductionRuntimeException failure = assertThrows(
                ProductionRuntimeException.class,
                () -> controller.complete(
                        "Bearer test", new ProductionRuntimeInternalController.CompletionRequest(
                                completion, null, null, null)));

        assertEquals("OUTPUT_VERIFICATION_REQUIRED", failure.code());
        verifyNoInteractions(coordinator);
    }

    @Test
    void verifiedSuccessUsesOnlyTheVerifiedCoordinatorPath() {
        Completion completion = completion(AttemptStatus.SUCCEEDED);
        OutputVerificationReceipt receipt = new OutputVerificationReceipt(
                OutputVerificationReceipt.SCHEMA_VERSION,
                "spring-modernization-v1",
                "SPRING_MODERNIZATION",
                "compile",
                "cas://sha256/" + "a".repeat(64),
                "a".repeat(64),
                "repository-owned-output-gate",
                "PASSED",
                "NOT_CERTIFIED",
                Map.of(
                        "target_build_pass", true,
                        "behavior_diff_pass", true,
                        "unresolved_p0_defects", 0));

        controller.complete(
                "Bearer test", new ProductionRuntimeInternalController.CompletionRequest(
                        completion, receipt, null, null));

        verify(coordinator).completeVerified(completion, receipt, null, null);
    }

    private static Completion completion(AttemptStatus status) {
        return new Completion(
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                UUID.randomUUID(), 1L, status,
                status == AttemptStatus.SUCCEEDED ? null : "FAILED", null);
    }
}
