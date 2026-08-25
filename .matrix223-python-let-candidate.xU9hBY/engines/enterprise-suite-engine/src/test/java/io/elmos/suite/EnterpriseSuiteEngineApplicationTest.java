package io.elmos.suite;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

class EnterpriseSuiteEngineApplicationTest {
    @Test void applicationTypeLoads() {
        assertDoesNotThrow(EnterpriseSuiteEngineApplication::new);
    }
}
