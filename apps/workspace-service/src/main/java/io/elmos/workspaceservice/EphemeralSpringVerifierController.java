package io.elmos.workspaceservice;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

import static io.elmos.workspaceservice.SpringRuntimeModels.Rejected;

@RestController
@ConditionalOnProperty(
        name = {"elmos.workspace.docker.enabled", "elmos.workspace.spring-verifier.enabled"},
        havingValue = "true"
)
final class EphemeralSpringVerifierController {
    private final EphemeralSpringVerifierBroker verifier;

    EphemeralSpringVerifierController(EphemeralSpringVerifierBroker verifier) {
        this.verifier = verifier;
    }

    @PostMapping(
            path = "/internal/v1/spring-verifications",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<byte[]> verify(
            @RequestHeader("X-ELMOS-Verifier-Timestamp") String timestamp,
            @RequestHeader("X-ELMOS-Verifier-Nonce") String nonce,
            @RequestHeader("X-ELMOS-Verifier-Signature") String signature,
            @RequestBody byte[] body
    ) {
        EphemeralSpringVerifierBroker.BrokerResponse response =
                verifier.verify(timestamp, nonce, signature, body);
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
                "message", "Verification request was rejected; use the stable code for controlled diagnostics."
        ));
    }
}
