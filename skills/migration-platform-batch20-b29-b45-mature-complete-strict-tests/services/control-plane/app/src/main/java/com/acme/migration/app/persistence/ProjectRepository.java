package com.acme.migration.app.persistence;

import com.acme.migration.domain.Models.Project;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.UUID;

@Repository
public class ProjectRepository {
    private final JdbcClient jdbc;

    public ProjectRepository(JdbcClient jdbc) { this.jdbc = jdbc; }

    public Project create(UUID tenantId, String name) {
        var project = new Project(UUID.randomUUID(), tenantId, name, Instant.now());
        jdbc.sql("""
                insert into platform.projects(project_id, tenant_id, name, created_at)
                values (:id, :tenant, :name, :created)
                """)
                .param("id", project.projectId())
                .param("tenant", project.tenantId())
                .param("name", project.name())
                .param("created", project.createdAt())
                .update();
        return project;
    }

    public long count(UUID tenantId) {
        return jdbc.sql("select count(*) from platform.projects where tenant_id = :tenant")
                .param("tenant", tenantId)
                .query(Long.class)
                .single();
    }
}
