package com.acme.migration.app.persistence;

import com.acme.migration.domain.Models.Migration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public class MigrationRepository {
    private final JdbcClient jdbc;

    public MigrationRepository(JdbcClient jdbc) { this.jdbc = jdbc; }

    public Migration create(UUID tenantId, UUID projectId, String sourceRepository,
                            String sourceLanguage, String targetLanguage, String targetFramework) {
        var now = Instant.now();
        var migration = new Migration(UUID.randomUUID(), tenantId, projectId, sourceRepository,
                sourceLanguage, targetLanguage, targetFramework,
                "planned", "intake", "medium", now, now);
        jdbc.sql("""
                insert into migration.migrations(
                    migration_id, tenant_id, project_id, source_repository,
                    source_language, target_language, target_framework,
                    status, current_phase, risk_tier, created_at, updated_at)
                values (:id, :tenant, :project, :repo, :sourceLang, :targetLang,
                        :framework, :status, :phase, :risk, :created, :updated)
                """)
                .param("id", migration.migrationId())
                .param("tenant", migration.tenantId())
                .param("project", migration.projectId())
                .param("repo", migration.sourceRepository())
                .param("sourceLang", migration.sourceLanguage())
                .param("targetLang", migration.targetLanguage())
                .param("framework", migration.targetFramework())
                .param("status", migration.status())
                .param("phase", migration.currentPhase())
                .param("risk", migration.riskTier())
                .param("created", migration.createdAt())
                .param("updated", migration.updatedAt())
                .update();
        return migration;
    }

    public Optional<Migration> find(UUID tenantId, UUID migrationId) {
        return jdbc.sql("""
                select * from migration.migrations
                where tenant_id = :tenant and migration_id = :id
                """)
                .param("tenant", tenantId)
                .param("id", migrationId)
                .query(this::map)
                .optional();
    }

    public List<Migration> recent(UUID tenantId, int limit) {
        return jdbc.sql("""
                select * from migration.migrations
                where tenant_id = :tenant
                order by created_at desc
                limit :limit
                """)
                .param("tenant", tenantId)
                .param("limit", limit)
                .query(this::map)
                .list();
    }

    public long count(UUID tenantId) {
        return jdbc.sql("select count(*) from migration.migrations where tenant_id = :tenant")
                .param("tenant", tenantId)
                .query(Long.class)
                .single();
    }

    private Migration map(ResultSet rs, int rowNum) throws SQLException {
        return new Migration(
                rs.getObject("migration_id", UUID.class),
                rs.getObject("tenant_id", UUID.class),
                rs.getObject("project_id", UUID.class),
                rs.getString("source_repository"),
                rs.getString("source_language"),
                rs.getString("target_language"),
                rs.getString("target_framework"),
                rs.getString("status"),
                rs.getString("current_phase"),
                rs.getString("risk_tier"),
                rs.getTimestamp("created_at").toInstant(),
                rs.getTimestamp("updated_at").toInstant());
    }
}
