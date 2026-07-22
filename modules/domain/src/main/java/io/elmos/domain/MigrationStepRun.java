package io.elmos.domain;

import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public final class MigrationStepRun {
    private final StepRunId id; private final String stepId; private final int attempt; private final String executorType; private StepState state=StepState.READY; private Instant startedAt; private Instant finishedAt; private final List<EvidenceId> evidenceIds=new ArrayList<>(); private String failureCode;
    public MigrationStepRun(StepRunId id,String stepId,int attempt,String executorType){if(id==null)throw new IllegalArgumentException("stepRunId required");if(attempt<1)throw new IllegalArgumentException("attempt must be positive");this.id=id;this.stepId=Identifiers.require(stepId,"stepId");this.attempt=attempt;this.executorType=Identifiers.require(executorType,"executorType");}
    public void start(Clock clock){if(state!=StepState.READY)throw new DomainException("only READY step can start");state=StepState.RUNNING;startedAt=clock.instant();}
    public void succeed(EvidenceId evidenceId,Clock clock){if(state!=StepState.RUNNING)throw new DomainException("only RUNNING step can succeed");if(evidenceId==null)throw new DomainException("successful step requires evidence");evidenceIds.add(evidenceId);state=StepState.SUCCEEDED;finishedAt=clock.instant();}
    public void fail(String code,boolean retryable,Clock clock){if(state!=StepState.RUNNING)throw new DomainException("only RUNNING step can fail");failureCode=Identifiers.require(code,"failureCode");state=retryable?StepState.FAILED_RETRYABLE:StepState.FAILED_FINAL;finishedAt=clock.instant();}
    public StepRunId id(){return id;} public String stepId(){return stepId;} public int attempt(){return attempt;} public String executorType(){return executorType;} public StepState state(){return state;} public Instant startedAt(){return startedAt;} public Instant finishedAt(){return finishedAt;} public List<EvidenceId> evidenceIds(){return List.copyOf(evidenceIds);} public String failureCode(){return failureCode;}
}

