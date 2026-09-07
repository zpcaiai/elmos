package io.elmos.databasedata;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

class DatabaseDataEngineControllerTest {
    private final DatabaseDataEngineController controller =
            new DatabaseDataEngineController(
                    new DatabaseDataEngineService(), mock(ChinaDbSqlPreflightGateway.class));

    @Test void exposesSharedEngineContractAndFailsClosed() {
        assertEquals("ELMOS_DATABASE_DATA", controller.capabilities().engineName());
        var response = controller.scan(new EngineApi.JobRequest("org-1", "snapshot-1",
                "workspace-1", "ORACLE", "corr-1", "scan-1"));
        assertEquals(EngineApi.JobStatus.FAILED, response.status());
        assertTrue(response.evidenceRefs().isEmpty());
    }
}
