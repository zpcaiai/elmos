package io.elmos.workspaceservice;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

import static io.elmos.workspaceservice.SpringRuntimeModels.Rejected;
import static io.elmos.workspaceservice.SpringRuntimeModels.Response;

@RestController
@ConditionalOnProperty(
        name = {"elmos.workspace.docker.enabled", "elmos.workspace.spring-runtime.enabled"},
        havingValue = "true"
)
final class SpringRuntimeController {
    private final RootlessSpringRuntimeService runtimes;

    SpringRuntimeController(RootlessSpringRuntimeService runtimes) {
        this.runtimes = runtimes;
    }

    @PostMapping(
            path = "/internal/v1/spring-runtimes",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Response handle(
            @RequestHeader("X-ELMOS-Runtime-Timestamp") String timestamp,
            @RequestHeader("X-ELMOS-Runtime-Nonce") String nonce,
            @RequestHeader("X-ELMOS-Runtime-Signature") String signature,
            @RequestBody byte[] body
    ) {
        return runtimes.handle(timestamp, nonce, signature, body);
    }

    @ExceptionHandler(Rejected.class)
    ResponseEntity<Map<String, String>> rejected(Rejected error) {
        HttpStatus status = "UNAUTHORIZED".equals(error.code())
                ? HttpStatus.UNAUTHORIZED
                : HttpStatus.UNPROCESSABLE_ENTITY;
        return ResponseEntity.status(status).body(Map.of(
                "status", "BLOCKED",
                "code", error.code(),
                "message", "Runtime request was rejected; use the stable code for controlled diagnostics."
        ));
    }
}
