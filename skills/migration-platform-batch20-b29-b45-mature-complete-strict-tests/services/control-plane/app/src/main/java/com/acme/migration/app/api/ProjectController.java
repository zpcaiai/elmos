package com.acme.migration.app.api;

import com.acme.migration.app.persistence.ProjectRepository;
import com.acme.migration.contracts.ApiContracts.CreateProjectRequest;
import com.acme.migration.contracts.ApiContracts.ProjectResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import static com.acme.migration.app.support.TenantContext.LOCAL_TENANT_ID;

@RestController
@RequestMapping("/api/v1/projects")
public class ProjectController {
    private final ProjectRepository projects;

    public ProjectController(ProjectRepository projects) { this.projects = projects; }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProjectResponse create(@Valid @RequestBody CreateProjectRequest request) {
        var project = projects.create(LOCAL_TENANT_ID, request.name());
        return new ProjectResponse(project.projectId(), project.tenantId(), project.name(), project.createdAt());
    }
}
