package com.acme.migration.app.persistence;

import com.acme.migration.domain.Models.Task;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public class RunnerRepository {
    private final JdbcClient jdbc;

    public RunnerRepository(JdbcClient jdbc) { this.jdbc = jdbc; }

    public UUID register(UUID tenantId, String name, String version, List<String> capabilities) {
        var id = UUID.randomUUID();
        jdbc.sql("""
                insert into runner.runners(
                  runner_id, tenant_id, name, version, capabilities, status,
                  registered_at, last_heartbeat_at)
                values (:id, :tenant, :name, :version, :capabilities, 'online', now(), now())
                """)
                .param("id", id)
                .param("tenant", tenantId)
                .param("name", name)
                .param("version", version)
                .param("capabilities", String.join(",", capabilities == null ? List.of() : capabilities))
                .update();
        return id;
    }

    public void heartbeat(UUID tenantId, UUID runnerId, String status) {
        int updated = jdbc.sql("""
                update runner.runners set status = :status, last_heartbeat_at = now()
                where tenant_id = :tenant and runner_id = :runner
                """)
                .param("status", status)
                .param("tenant", tenantId)
                .param("runner", runnerId)
                .update();
        if (updated != 1) throw new IllegalArgumentException("runner not found");
    }

    public long onlineCount(UUID tenantId) {
        return jdbc.sql("""
                select count(*) from runner.runners
                where tenant_id = :tenant and last_heartbeat_at > now() - interval '30 seconds'
                """)
                .param("tenant", tenantId)
                .query(Long.class)
                .single();
    }

    public UUID enqueue(UUID tenantId, UUID workflowId, String taskType, String payload) {
        var taskId = UUID.randomUUID();
        jdbc.sql("""
                insert into workflow.tasks(
                    task_id, tenant_id, workflow_instance_id, task_type, status,
                    priority, attempt, max_attempts, payload, created_at, updated_at)
                values (:id, :tenant, :workflow, :type, 'queued', 100, 0, 3,
                        cast(:payload as jsonb), now(), now())
                """)
                .param("id", taskId)
                .param("tenant", tenantId)
                .param("workflow", workflowId)
                .param("type", taskType)
                .param("payload", payload)
                .update();
        return taskId;
    }

    public long queuedCount(UUID tenantId) {
        return jdbc.sql("""
                select count(*) from workflow.tasks
                where tenant_id = :tenant and status = 'queued'
                """)
                .param("tenant", tenantId)
                .query(Long.class)
                .single();
    }

    @Transactional
    public Optional<Task> claim(UUID tenantId, UUID runnerId) {
        jdbc.sql("""
                update workflow.tasks
                set status = 'queued', leased_by = null, lease_expires_at = null,
                    commit_token = null, updated_at = now()
                where tenant_id = :tenant and status = 'leased' and lease_expires_at < now()
                """)
                .param("tenant", tenantId)
                .update();
        var candidate = jdbc.sql("""
                select task_id, tenant_id, workflow_instance_id, task_type, status,
                       priority, attempt, max_attempts, payload::text
                from workflow.tasks
                where tenant_id = :tenant
                  and status = 'queued'
                  and attempt < max_attempts
                order by priority desc, created_at
                for update skip locked
                limit 1
                """)
                .param("tenant", tenantId)
                .query((rs, rowNum) -> new Task(
                        rs.getObject("task_id", UUID.class),
                        rs.getObject("tenant_id", UUID.class),
                        rs.getObject("workflow_instance_id", UUID.class),
                        rs.getString("task_type"),
                        rs.getString("status"),
                        rs.getInt("priority"),
                        rs.getInt("attempt"),
                        rs.getInt("max_attempts"),
                        rs.getString("payload"),
                        null, null, null))
                .optional();
        if (candidate.isEmpty()) return Optional.empty();

        var task = candidate.get();
        var leaseExpiry = Instant.now().plus(45, ChronoUnit.SECONDS);
        var token = UUID.randomUUID().toString();
        jdbc.sql("""
                update workflow.tasks
                set status = 'leased', leased_by = :runner,
                    lease_expires_at = :expires, commit_token = :token,
                    attempt = attempt + 1, updated_at = now()
                where task_id = :task
                """)
                .param("runner", runnerId)
                .param("expires", leaseExpiry)
                .param("token", token)
                .param("task", task.taskId())
                .update();
        return Optional.of(new Task(task.taskId(), task.tenantId(), task.workflowInstanceId(),
                task.taskType(), "leased", task.priority(), task.attempt() + 1,
                task.maxAttempts(), task.payload(), runnerId, leaseExpiry, token));
    }

    @Transactional
    public void complete(UUID tenantId, UUID taskId, String commitToken, String status,
                         String outputPayload, String artifactPath) {
        int updated = jdbc.sql("""
                update workflow.tasks
                set status = :status,
                    output_payload = cast(:output as jsonb),
                    artifact_path = :artifact,
                    completed_at = now(), updated_at = now()
                where tenant_id = :tenant and task_id = :task
                  and commit_token = :token and status = 'leased'
                """)
                .param("status", status)
                .param("output", outputPayload == null || outputPayload.isBlank() ? "{}" : outputPayload)
                .param("artifact", artifactPath)
                .param("tenant", tenantId)
                .param("task", taskId)
                .param("token", commitToken)
                .update();
        if (updated != 1) throw new IllegalStateException("task completion rejected: lease or commit token mismatch");
    }
}
