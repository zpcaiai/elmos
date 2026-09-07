package com.acme.migration.app.api;

import com.acme.migration.app.persistence.MigrationRepository;
import com.acme.migration.app.persistence.ProjectRepository;
import com.acme.migration.app.persistence.RunnerRepository;
import com.acme.migration.contracts.ApiContracts.DemoBootstrapResponse;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import static com.acme.migration.app.support.TenantContext.LOCAL_TENANT_ID;

@RestController
@RequestMapping("/api/v1/demo")
public class DemoController {
    private final ProjectRepository projects;
    private final MigrationRepository migrations;
    private final RunnerRepository runners;

    public DemoController(ProjectRepository projects, MigrationRepository migrations, RunnerRepository runners) {
        this.projects = projects;
        this.migrations = migrations;
        this.runners = runners;
    }

    @PostMapping("/bootstrap")
    @ResponseStatus(HttpStatus.CREATED)
    public DemoBootstrapResponse bootstrap() {
        var project = projects.create(LOCAL_TENANT_ID, "Batch 20 Demo");
        var migration = migrations.create(LOCAL_TENANT_ID, project.projectId(),
                "samples/java-sample", "java", "csharp", "aspnet-core");
        var payload = """
                {"migration_id":"%s","message":"runner execution proved"}
                """.formatted(migration.migrationId()).trim();
        var taskId = runners.enqueue(LOCAL_TENANT_ID, migration.migrationId(), "echo-artifact", payload);
        return new DemoBootstrapResponse(project.projectId(), migration.migrationId(), taskId);
    }
}
