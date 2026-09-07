package io.elmos.application;

import io.elmos.domain.*;
import io.elmos.evidence.*;

import java.time.Clock;
import java.util.List;
import java.util.UUID;

public final class BatchOneDemoService {
    private final DemoPersistencePort persistence; private final Clock clock;
    public BatchOneDemoService(DemoPersistencePort persistence, Clock clock) { this.persistence=persistence; this.clock=clock; }

    public DemoRunResult execute() {
        var orgId=OrganizationId.random();
        var repository=new Repository(RepositoryId.random(),orgId,"GITHUB","demo/legacy-spring","main");
        var source=new CommitSha("0123456789abcdef0123456789abcdef01234567");
        var target=new CommitSha("89abcdef0123456789abcdef0123456789abcdef");
        var snapshot=new RepositorySnapshot(SnapshotId.random(),orgId,repository.id(),source,"main",clock.instant(),"sha256:"+"1".repeat(64),new ArtifactRef("s3://elmos-demo/source.tar.zst"));
        var assessment=AssessmentRun.completed(orgId,snapshot.id(),clock.instant());
        var plan=new MigrationPlan(MigrationPlanId.random(),orgId,snapshot.id(),1,"java11-spring-boot2-maven","java21-spring-boot3-maven",
                List.of(new MigrationPlan.Step("simulate-openrewrite","OPENREWRITE",List.of(),false)));
        plan.approve("human-reviewer",clock);
        var run=new MigrationRun(MigrationRunId.random(),orgId,snapshot.id(),plan.id(),plan.version(),clock);
        run.prepareRepository(); run.fingerprint(); run.baseline(); run.recordBaseline(true); run.planGenerated(); run.startMigration(plan);
        var step=run.startStep(plan.steps().getFirst());
        var evidence=new Evidence(EvidenceId.random(),orgId,run.id(),step.id(),EvidenceType.BUILD_RESULT,"JAVA_ENGINE","batch1-simulator","0.1.0",source,target,clock.instant(),EvidenceStatus.PASS,"Simulated worker evidence; no customer code was executed",new ArtifactRef("s3://elmos-demo/evidence/build-result.json"),"sha256:"+"2".repeat(64),"1.0",UUID.randomUUID().toString());
        run.completeStep(step,evidence.evidenceId()); run.validate(); run.recordValidation(true); run.approveDelivery(); run.deliver();
        var audit=List.of(
                new AuditEvent(UUID.randomUUID().toString(),"HUMAN","human-reviewer","APPROVE_PLAN","MIGRATION_PLAN",plan.id().value(),null,"sha256:"+"3".repeat(64),clock.instant(),UUID.randomUUID().toString(),null,"ALLOW","SUCCESS"),
                new AuditEvent(UUID.randomUUID().toString(),"WORKER","batch1-simulator","COMPLETE_STEP","MIGRATION_RUN",run.id().value(),null,"sha256:"+"4".repeat(64),clock.instant(),UUID.randomUUID().toString(),"worker-demo","ALLOW","SUCCESS"));
        var events=run.pullEvents();
        persistence.save(new DemoRecord(repository,snapshot,assessment,plan,run,step,evidence,audit,events));
        return new DemoRunResult(repository.id().value(),snapshot.id().value(),assessment.id(),plan.id().value(),plan.version(),run.id().value(),run.state(),step.id().value(),step.state(),evidence.evidenceId().value(),evidence.status(),audit.size(),events.size(),true);
    }
}

