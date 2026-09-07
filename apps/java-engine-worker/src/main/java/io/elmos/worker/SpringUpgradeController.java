package io.elmos.worker;

import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static io.elmos.worker.SpringUpgradeModels.*;

@RestController
@RequestMapping("/engine/v1/spring-upgrades")
final class SpringUpgradeController {
    record RetryRequest(String idempotencyKey) {}

    private final SpringUpgradeRunService service;

    SpringUpgradeController(SpringUpgradeRunService service) {
        this.service = service;
    }

    @GetMapping("/capabilities")
    Map<String, Object> capabilities() {
        return service.capabilities();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.ACCEPTED)
    RunView create(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestBody StartRequest request
    ) {
        return service.create(organizationId, request);
    }

    @GetMapping("/{runId}")
    RunView get(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @PathVariable String runId
    ) {
        return service.get(organizationId, runId);
    }

    @GetMapping("/{runId}/logs")
    LogView logs(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @PathVariable String runId
    ) {
        return service.logs(organizationId, runId);
    }

    @GetMapping("/{runId}/artifact")
    ResponseEntity<FileSystemResource> artifact(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @PathVariable String runId
    ) throws IOException {
        RunView view = service.get(organizationId, runId);
        Path artifact = service.artifact(organizationId, runId);
        String digest = view.artifactSha256();
        String targetBoot = view.exactTuple().targetSpringBoot();
        if (digest == null || !digest.matches("[0-9a-f]{64}")) {
            throw new IllegalStateException("ARTIFACT_DIGEST_UNAVAILABLE");
        }
        if (targetBoot == null || !targetBoot.matches("[0-9]+\\.[0-9]+\\.[0-9]+")) {
            throw new IllegalStateException("TARGET_TUPLE_UNAVAILABLE");
        }
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(Files.size(artifact))
                .eTag("\"" + digest + "\"")
                .header("X-Content-SHA256", digest)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename("migrated-spring-boot-" + targetBoot + ".zip")
                                .build().toString())
                .body(new FileSystemResource(artifact));
    }

    @PostMapping("/{runId}/runtime/start")
    @ResponseStatus(HttpStatus.ACCEPTED)
    RunView start(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @PathVariable String runId
    ) {
        return service.startRuntime(organizationId, runId);
    }

    @PostMapping("/{runId}/runtime/stop")
    RunView stop(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @PathVariable String runId
    ) {
        return service.stopRuntime(organizationId, runId);
    }

    @PostMapping("/{runId}/retry")
    @ResponseStatus(HttpStatus.ACCEPTED)
    RunView retry(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @PathVariable String runId,
            @RequestBody RetryRequest request
    ) {
        return service.retry(organizationId, runId, request.idempotencyKey());
    }

    @PostMapping("/{runId}/cancel")
    RunView cancel(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @PathVariable String runId
    ) {
        return service.cancel(organizationId, runId);
    }

    @ExceptionHandler(SpringUpgradeRunService.NotFound.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    Map<String, Object> notFound() {
        return error("SPRING_UPGRADE_RUN_NOT_FOUND", "The migration run was not found.", false);
    }

    @ExceptionHandler(SpringUpgradeRunService.IdempotencyConflict.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    Map<String, Object> idempotencyConflict() {
        return error("SPRING_UPGRADE_IDEMPOTENCY_CONFLICT",
                "The idempotency key was already used with different migration input.", false);
    }

    @ExceptionHandler(SpringUpgradeRunService.Conflict.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    Map<String, Object> conflict(SpringUpgradeRunService.Conflict error) {
        return error(error.code(), "The requested lifecycle action is not valid in the current state.", false);
    }

    @ExceptionHandler({
            SpringUpgradeRunService.InvalidRequest.class,
            org.springframework.http.converter.HttpMessageNotReadableException.class
    })
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> invalidRequest() {
        return error(
                "SPRING_UPGRADE_REQUEST_INVALID",
                "The migration request is invalid or malformed.",
                false
        );
    }

    private static Map<String, Object> error(String code, String message, boolean retryable) {
        return Map.of("errorCode", code, "message", message, "retryable", retryable);
    }
}
