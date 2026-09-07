package com.acme.migration.app.api;

import com.acme.migration.app.persistence.MigrationRepository;
import com.acme.migration.contracts.ApiContracts.CreateMigrationRequest;
import com.acme.migration.contracts.ApiContracts.MigrationResponse;
import com.acme.migration.domain.Models.Migration;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.UUID;

import static com.acme.migration.app.support.TenantContext.LOCAL_TENANT_ID;

@RestController
@RequestMapping("/api/v1/migrations")
public class MigrationController {
    private final MigrationRepository migrations;

    public MigrationController(MigrationRepository migrations) { this.migrations = migrations; }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public MigrationResponse create(@Valid @RequestBody CreateMigrationRequest request) {
        return response(migrations.create(LOCAL_TENANT_ID, request.projectId(), request.sourceRepository(),
                request.sourceLanguage(), request.targetLanguage(), request.targetFramework()));
    }

    @GetMapping("/{migrationId}")
    public MigrationResponse get(@PathVariable UUID migrationId) {
        return migrations.find(LOCAL_TENANT_ID, migrationId)
                .map(MigrationController::response)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    static MigrationResponse response(Migration migration) {
        return new MigrationResponse(migration.migrationId(), migration.tenantId(), migration.projectId(),
                migration.sourceRepository(), migration.sourceLanguage(), migration.targetLanguage(),
                migration.targetFramework(), migration.status(), migration.currentPhase(), migration.riskTier(),
                migration.createdAt(), migration.updatedAt());
    }
}
