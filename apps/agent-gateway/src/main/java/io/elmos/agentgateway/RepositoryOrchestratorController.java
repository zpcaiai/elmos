package io.elmos.agentgateway;

import com.fasterxml.jackson.databind.JsonNode;
import io.elmos.repair.RepositoryTaskRouterModels.Catalog;
import io.elmos.repair.RepositoryTaskRouterModels.PreflightResult;
import io.elmos.repair.RepositoryTaskRouterService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Objects;

/** Planning-only repository task-router API. No execution authority is wired here. */
@RestController
@RequestMapping("/agent/v1/repository-orchestrator")
public final class RepositoryOrchestratorController {
    private final RepositoryTaskRouterService service;

    public RepositoryOrchestratorController() {
        this(new RepositoryTaskRouterService());
    }

    RepositoryOrchestratorController(RepositoryTaskRouterService service) {
        this.service = Objects.requireNonNull(service);
    }

    @GetMapping("/models")
    public Catalog models() {
        return service.catalog();
    }

    @PostMapping("/preflight")
    public ResponseEntity<PreflightResult> preflight(@RequestBody JsonNode request) {
        PreflightResult result = service.preflight(request, "api");
        return ResponseEntity.status(result.invalidRequest() ? HttpStatus.BAD_REQUEST : HttpStatus.OK).body(result);
    }
}
