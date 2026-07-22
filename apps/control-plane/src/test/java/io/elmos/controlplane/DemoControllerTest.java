package io.elmos.controlplane;

import io.elmos.application.BatchOneDemoService;
import io.elmos.domain.MigrationState;
import org.junit.jupiter.api.Test;
import java.time.Clock;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DemoControllerTest {
    @Test void endpointReturnsPersistedDemoSummary(){var controller=new DemoController(new BatchOneDemoService(record->{},Clock.systemUTC()));assertEquals(MigrationState.DELIVERED,controller.create().state());}
}

