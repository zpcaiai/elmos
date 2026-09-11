package io.elmos.worker;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = JavaEngineWorkerApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "elmos.worker.spring-upgrade.enabled=false",
                "elmos.worker.spring-upgrade.ingress-auth-enabled=false",
                "management.endpoints.web.exposure.include=health,info,prometheus",
                "spring.cloud.compatibility-verifier.enabled=false",
                "spring.cloud.gateway.enabled=false"
        }
)
@AutoConfigureObservability
public class SpringWorkerPrometheusEndpointTest {
    @Autowired
    private TestRestTemplate http;

    @Test
    void exportsPrometheusMetricsOnTheInternalActuatorEndpoint() {
        ResponseEntity<String> health = http.getForEntity("/actuator/health", String.class);
        assertEquals(HttpStatus.OK, health.getStatusCode());

        ResponseEntity<String> capabilities = http.getForEntity("/engine/v1/capabilities", String.class);
        assertEquals(HttpStatus.OK, capabilities.getStatusCode());

        ResponseEntity<String> springCapabilities = http.getForEntity(
                "/engine/v1/spring-upgrades/capabilities", String.class);
        assertEquals(HttpStatus.OK, springCapabilities.getStatusCode());

        HttpHeaders springIdentity = new HttpHeaders();
        springIdentity.set("X-ELMOS-Organization-ID", "spring-production-e2e");
        ResponseEntity<String> missingSpringRun = http.exchange(
                "/engine/v1/spring-upgrades/123e4567-e89b-42d3-a456-426614174000",
                HttpMethod.GET,
                new HttpEntity<>(springIdentity),
                String.class);
        assertEquals(HttpStatus.NOT_FOUND, missingSpringRun.getStatusCode());

        ResponseEntity<String> unrelatedMutation = http.postForEntity(
                "/engine/v1/recipes/selections", "{}", String.class);
        assertEquals(HttpStatus.FORBIDDEN, unrelatedMutation.getStatusCode());

        ResponseEntity<String> metrics = http.getForEntity("/actuator/prometheus", String.class);
        assertEquals(HttpStatus.OK, metrics.getStatusCode());
        assertNotNull(metrics.getBody());
        assertTrue(metrics.getBody().contains("jvm_info"));
        assertTrue(metrics.getBody().contains("http_server_requests_seconds"));
    }
}
