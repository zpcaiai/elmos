package io.elmos.verifier;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

import static io.elmos.verifier.VerificationModels.Rejected;
import static io.elmos.verifier.VerificationModels.Response;

@RestController
final class SpringVerificationController {
    private final SpringArtifactVerifier verifier;

    SpringVerificationController(SpringArtifactVerifier verifier) {
        this.verifier = verifier;
    }

    @PostMapping(
            path = "/internal/v1/spring-verifications",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Response verify(
            @RequestHeader("X-ELMOS-Verifier-Timestamp") String timestamp,
            @RequestHeader("X-ELMOS-Verifier-Nonce") String nonce,
            @RequestHeader("X-ELMOS-Verifier-Signature") String signature,
            @RequestBody byte[] body
    ) {
        return verifier.verify(timestamp, nonce, signature, body);
    }

    @ExceptionHandler(Rejected.class)
    ResponseEntity<Map<String, String>> rejected(Rejected error) {
        HttpStatus status = "UNAUTHORIZED".equals(error.code())
                ? HttpStatus.UNAUTHORIZED
                : HttpStatus.UNPROCESSABLE_ENTITY;
        return ResponseEntity.status(status).body(Map.of(
                "status", "BLOCKED",
                "code", error.code(),
                "message", "The verification request was rejected."
        ));
    }
}
