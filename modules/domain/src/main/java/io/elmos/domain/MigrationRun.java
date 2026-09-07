package io.elmos.domain;

import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class MigrationRun {
    private final MigrationRunId id; private final OrganizationId organizationId; private final SnapshotId snapshotId; private final MigrationPlanId planId; private final int planVersion; private final Clock clock;
    private final List<DomainEvent> events=new ArrayList<>(); private final List<MigrationStepRun> stepRuns=new ArrayList<>();
    private final Map<String, MigrationPlan.Step> approvedSteps=new LinkedHashMap<>();
    private MigrationState state=MigrationState.CREATED; private long version;
    public MigrationRun(MigrationRunId id,OrganizationId organizationId,SnapshotId snapshotId,MigrationPlanId planId,int planVersion,Clock clock){if(id==null||organizationId==null||snapshotId==null||planId==null||clock==null)throw new IllegalArgumentException("run fields required");if(planVersion<1)throw new IllegalArgumentException("planVersion must be positive");this.id=id;this.organizationId=organizationId;this.snapshotId=snapshotId;this.planId=planId;this.planVersion=planVersion;this.clock=clock;emit("MigrationCreated");}
    public void prepareRepository(){move(MigrationState.CREATED,MigrationState.REPOSITORY_PREPARING,"RepositoryPreparationStarted");}
    public void fingerprint(){move(MigrationState.REPOSITORY_PREPARING,MigrationState.FINGERPRINTING,"AssessmentStarted");}
    public void baseline(){move(MigrationState.FINGERPRINTING,MigrationState.BASELINING,"BaselineStarted");}
    public void recordBaseline(boolean passed){move(MigrationState.BASELINING,passed?MigrationState.PLAN_GENERATING:MigrationState.BASELINE_BROKEN,"BaselineCompleted");}
    public void planGenerated(){move(MigrationState.PLAN_GENERATING,MigrationState.AWAITING_PLAN_APPROVAL,"MigrationPlanGenerated");}
    public void startMigration(MigrationPlan plan){if(plan==null||plan.status()!=MigrationPlan.Status.APPROVED)throw new DomainException("approved plan required");if(!plan.id().equals(planId)||plan.version()!=planVersion||!plan.organizationId().equals(organizationId)||!plan.snapshotId().equals(snapshotId))throw new DomainException("plan does not belong to run");approvedSteps.clear();for(var step:plan.steps())approvedSteps.put(step.id(),step);move(MigrationState.AWAITING_PLAN_APPROVAL,MigrationState.MIGRATING,"MigrationStarted");}
    public MigrationStepRun startStep(MigrationPlan.Step step){
        require(MigrationState.MIGRATING);
        if(step==null)throw new DomainException("step is required");
        var approvedStep=approvedSteps.get(step.id());
        if(approvedStep==null||!approvedStep.equals(step))throw new DomainException("step does not belong to approved plan");
        for(var dependency:approvedStep.dependencies())if(latestStepState(dependency)!=StepState.SUCCEEDED)throw new DomainException("dependency not completed: "+dependency);
        var previous=latestStepRun(step.id());
        if(previous!=null&&previous.state()!=StepState.FAILED_RETRYABLE)throw new DomainException("step already started: "+step.id());
        int attempt=previous==null?1:previous.attempt()+1;
        var run=new MigrationStepRun(StepRunId.random(),step.id(),attempt,step.executorType());run.start(clock);stepRuns.add(run);emit("MigrationStepStarted");return run;
    }
    public void completeStep(MigrationStepRun step,EvidenceId evidenceId){require(MigrationState.MIGRATING);if(!stepRuns.contains(step))throw new DomainException("step does not belong to run");step.succeed(evidenceId,clock);emit("MigrationStepCompleted");}
    public void failStep(MigrationStepRun step,String failureCode,boolean retryable){require(MigrationState.MIGRATING);if(!stepRuns.contains(step))throw new DomainException("step does not belong to run");step.fail(failureCode,retryable,clock);emit("MigrationStepFailed");}
    public void validate(){require(MigrationState.MIGRATING);for(var stepId:approvedSteps.keySet())if(latestStepState(stepId)!=StepState.SUCCEEDED)throw new DomainException("all approved steps must succeed before validation: "+stepId);move(MigrationState.MIGRATING,MigrationState.VALIDATING,"ValidationStarted");}
    public void recordValidation(boolean passed){move(MigrationState.VALIDATING,passed?MigrationState.AWAITING_FINAL_REVIEW:MigrationState.VALIDATION_FAILED,"ValidationCompleted");}
    public void approveDelivery(){move(MigrationState.AWAITING_FINAL_REVIEW,MigrationState.PUBLISHING,"FinalReviewApproved");}
    public void deliver(){move(MigrationState.PUBLISHING,MigrationState.DELIVERED,"MigrationDelivered");}
    public void cancel(){if(state.terminal())throw new DomainException("terminal run cannot be cancelled");state=MigrationState.CANCELLED;version++;emit("MigrationCancelled");}
    private MigrationStepRun latestStepRun(String stepId){for(int i=stepRuns.size()-1;i>=0;i--)if(stepRuns.get(i).stepId().equals(stepId))return stepRuns.get(i);return null;}
    private StepState latestStepState(String stepId){var run=latestStepRun(stepId);return run==null?null:run.state();}
    private void move(MigrationState from,MigrationState to,String event){require(from);state=to;version++;emit(event);} private void require(MigrationState expected){if(state!=expected)throw new DomainException("expected "+expected+" but was "+state);} private void emit(String type){events.add(new DomainEvent(Identifiers.random(),type,id.value(),clock.instant(),java.util.Map.of("state",state.name())));}
    public List<DomainEvent> pullEvents(){var copy=List.copyOf(events);events.clear();return copy;} public MigrationRunId id(){return id;} public OrganizationId organizationId(){return organizationId;} public SnapshotId snapshotId(){return snapshotId;} public MigrationPlanId planId(){return planId;} public int planVersion(){return planVersion;} public MigrationState state(){return state;} public long version(){return version;} public List<MigrationStepRun> stepRuns(){return List.copyOf(stepRuns);}
}
