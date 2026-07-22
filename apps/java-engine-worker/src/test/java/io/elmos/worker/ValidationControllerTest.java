package io.elmos.worker;

import io.elmos.validation.ValidationModels.*;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

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
}
