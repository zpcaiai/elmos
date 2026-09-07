package io.elmos.workspaceservice;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

import static io.elmos.workspaceservice.SpringRuntimeModels.Rejected;

@RestController
@ConditionalOnProperty(
        name = {"elmos.workspace.docker.enabled", "elmos.workspace.spring-transformer.enabled"},
        havingValue = "true"
)
final class EphemeralSpringTransformerController {
    private final EphemeralSpringTransformerBroker broker;

    EphemeralSpringTransformerController(EphemeralSpringTransformerBroker broker) {
        this.broker = broker;
    }

    @PostMapping(
            path = "/internal/v1/spring-transformations",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<byte[]> handle(
            @RequestHeader("X-ELMOS-Transformer-Timestamp") String timestamp,
            @RequestHeader("X-ELMOS-Transformer-Nonce") String nonce,
            @RequestHeader("X-ELMOS-Transformer-Signature") String signature,
            @RequestBody byte[] body
    ) {
        EphemeralSpringTransformerBroker.BrokerResponse response =
                broker.handle(timestamp, nonce, signature, body);
        return ResponseEntity.status(response.status())
                .contentType(MediaType.APPLICATION_JSON)
                .body(response.body());
    }

    @ExceptionHandler(Rejected.class)
    ResponseEntity<Map<String, String>> rejected(Rejected error) {
        HttpStatus status = "UNAUTHORIZED".equals(error.code())
                ? HttpStatus.UNAUTHORIZED
                : HttpStatus.UNPROCESSABLE_ENTITY;
        return ResponseEntity.status(status).body(Map.of(
                "status", "BLOCKED",
                "code", error.code(),
                "message", "Transformation request was rejected; use the stable code for controlled diagnostics."
        ));
    }
}
