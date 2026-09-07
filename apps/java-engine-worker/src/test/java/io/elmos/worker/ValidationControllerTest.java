package io.elmos.worker;

import io.elmos.validation.ValidationModels.*;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ValidationControllerTest {
    @Test void silentTestRemovalCannotPassThroughWorkerApi() {
        var before = new TestCase("junit", "A", "works", "", TestStatus.PASSED, null, 1, false);
        var result = new ValidationController().tests(new ValidationController.TestRequest(List.of(before), List.of()));
        assertEquals(Status.FAIL, result.status());
    }

    @Test void cleanTestComparisonWithoutEvidenceIsInconclusive() {
        var test = new TestCase("junit", "A", "works", "", TestStatus.PASSED, null, 1, false);
        var result = new ValidationController().tests(new ValidationController.TestRequest(List.of(test), List.of(test)));
        assertEquals(Status.INCONCLUSIVE, result.status());
    }

    @Test void missingComparisonSidesAreRejectedBeforeEnteringTheJudge() {
        assertThrows(IllegalArgumentException.class,
                () -> new ValidationController.EnvironmentRequest(null, null));
        assertThrows(IllegalArgumentException.class,
                () -> new ValidationController.TestRequest(null, List.of(), List.of()));
    }

    @Test void invertedOrNonFinitePerformanceThresholdsAreRejected() {
        var sample = new PerformanceSample("scenario", List.of(1.0), 1, 1, 1, "env");
        assertThrows(IllegalArgumentException.class,
                () -> new ValidationController.PerformanceRequest(sample, sample, .2, .1, .1, List.of()));
        assertThrows(IllegalArgumentException.class,
                () -> new ValidationController.PerformanceRequest(sample, sample, Double.NaN, .1, .1, List.of()));
    }

    @Test void invalidRequestsHaveAStableSafeContract() {
        var response = new ValidationController().invalidRequest(new IllegalArgumentException("internal detail"));
        assertEquals("VALIDATION_REQUEST_INVALID", response.get("errorCode"));
        assertEquals(false, response.get("retryable"));
    }
}
