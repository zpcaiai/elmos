package io.elmos.persistence;

import io.elmos.application.DemoPersistencePort;
import io.elmos.application.DemoRecord;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class JdbcDemoPersistence implements DemoPersistencePort {
    private final JdbcTemplate jdbc;
    public JdbcDemoPersistence(JdbcTemplate jdbc) { this.jdbc=jdbc; }

    @Override @Transactional
    public void save(DemoRecord r) {
        var org=r.repository().organizationId().value();
        jdbc.update("insert into organizations(organization_id) values (?)",org);
        jdbc.update("insert into repositories(repository_id,organization_id,scm_provider,external_id,default_branch) values (?,?,?,?,?)",r.repository().id().value(),org,r.repository().scmProvider(),r.repository().externalId(),r.repository().defaultBranch());
        jdbc.update("insert into repository_snapshots(snapshot_id,organization_id,repository_id,commit_sha,requested_ref,captured_at,build_files_hash,archive_artifact_ref) values (?,?,?,?,?,?,?,?)",r.snapshot().id().value(),org,r.repository().id().value(),r.snapshot().commitSha().value(),r.snapshot().branch(),r.snapshot().capturedAt(),r.snapshot().buildFilesHash(),r.snapshot().sourceArchiveRef().value());
        jdbc.update("insert into assessment_runs(assessment_run_id,organization_id,snapshot_id,status,started_at,completed_at) values (?,?,?,?,?,?)",r.assessment().id(),org,r.snapshot().id().value(),r.assessment().status().name(),r.assessment().startedAt(),r.assessment().completedAt());
        jdbc.update("insert into migration_plans(migration_plan_id,organization_id,snapshot_id,plan_version,status,source_profile,target_profile,approved_at,approved_by) values (?,?,?,?,?,?,?,?,?)",r.plan().id().value(),org,r.snapshot().id().value(),r.plan().version(),r.plan().status().name(),r.plan().sourceProfile(),r.plan().targetProfile(),r.plan().approvedAt(),r.plan().approvedBy());
        jdbc.update("insert into migration_runs(migration_run_id,organization_id,snapshot_id,migration_plan_id,plan_version,state,version) values (?,?,?,?,?,?,?)",r.run().id().value(),org,r.snapshot().id().value(),r.plan().id().value(),r.plan().version(),r.run().state().name(),r.run().version());
        jdbc.update("insert into migration_step_runs(step_run_id,migration_run_id,step_id,attempt,executor_type,state,started_at,finished_at,failure_code) values (?,?,?,?,?,?,?,?,?)",r.step().id().value(),r.run().id().value(),r.step().stepId(),r.step().attempt(),r.step().executorType(),r.step().state().name(),r.step().startedAt(),r.step().finishedAt(),r.step().failureCode());
        var e=r.evidence();
        jdbc.update("insert into evidence(evidence_id,organization_id,migration_run_id,step_run_id,evidence_type,producer_type,producer_name,producer_version,source_commit,target_commit,created_at,status,summary,artifact_ref,content_hash,schema_version,correlation_id) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",e.evidenceId().value(),org,e.migrationRunId().value(),e.stepRunId().value(),e.evidenceType().name(),e.producerType(),e.producerName(),e.producerVersion(),e.sourceCommit().value(),e.targetCommit().value(),e.createdAt(),e.status().name(),e.summary(),e.artifactRef().value(),e.contentHash(),e.schemaVersion(),e.correlationId());
        r.auditEvents().forEach(a->jdbc.update("insert into audit_events(audit_id,actor_type,actor_id,action,resource_type,resource_id,before_hash,after_hash,occurred_at,request_id,runner_id,policy_decision,result) values (?,?,?,?,?,?,?,?,?,?,?,?,?)",a.auditId(),a.actorType(),a.actorId(),a.action(),a.resourceType(),a.resourceId(),a.beforeHash(),a.afterHash(),a.timestamp(),a.requestId(),a.runnerId(),a.policyDecision(),a.result()));
        r.domainEvents().forEach(d->jdbc.update("insert into outbox_events(event_id,aggregate_type,aggregate_id,event_type,occurred_at,attributes) values (?,?,?,?,?,?)",d.eventId(),"MIGRATION_RUN",d.aggregateId(),d.eventType(),d.occurredAt(),d.attributes().toString()));
    }
}
