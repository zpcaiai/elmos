package com.acme.migration.app.api;

import com.acme.migration.app.persistence.MigrationRepository;
import com.acme.migration.app.persistence.ProjectRepository;
import com.acme.migration.app.persistence.RunnerRepository;
import com.acme.migration.contracts.ApiContracts.OverviewResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static com.acme.migration.app.support.TenantContext.LOCAL_TENANT_ID;

@RestController
@RequestMapping("/api/v1/overview")
public class OverviewController {
    private final ProjectRepository projects;
    private final MigrationRepository migrations;
    private final RunnerRepository runners;

    public OverviewController(ProjectRepository projects, MigrationRepository migrations, RunnerRepository runners) {
        this.projects = projects;
        this.migrations = migrations;
        this.runners = runners;
    }

    @GetMapping
    public OverviewResponse overview() {
        return new OverviewResponse(
                projects.count(LOCAL_TENANT_ID),
                migrations.count(LOCAL_TENANT_ID),
                runners.queuedCount(LOCAL_TENANT_ID),
                runners.onlineCount(LOCAL_TENANT_ID),
                migrations.recent(LOCAL_TENANT_ID, 5).stream().map(MigrationController::response).toList());
    }
}
