package io.elmos.worker;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "elmos.worker.spring-upgrade.enabled=false",
                "elmos.worker.spring-upgrade.ingress-auth-enabled=false",
                "management.endpoints.web.exposure.include=health,info,prometheus"
        }
)
@AutoConfigureObservability
class SpringWorkerPrometheusEndpointTest {
    @Autowired
    private TestRestTemplate http;

    @Test
    void exportsPrometheusMetricsOnTheInternalActuatorEndpoint() {
        ResponseEntity<String> health = http.getForEntity("/actuator/health", String.class);
        assertEquals(HttpStatus.OK, health.getStatusCode());

        ResponseEntity<String> metrics = http.getForEntity("/actuator/prometheus", String.class);
        assertEquals(HttpStatus.OK, metrics.getStatusCode());
        assertNotNull(metrics.getBody());
        assertTrue(metrics.getBody().contains("jvm_info"));
        assertTrue(metrics.getBody().contains("http_server_requests_seconds"));
    }
}
