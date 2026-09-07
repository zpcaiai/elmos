package io.elmos.portfolio;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static io.elmos.portfolio.PortfolioScaleModels.requireText;

public final class PortfolioControlTower {
    public enum WorkState { QUEUED, RUNNING, SUCCEEDED, FAILED, BLOCKED, UNKNOWN }
    public record Observation(String workUnitId, String repositoryId, WorkState state,
                              long observedAtEpochMillis, long costUnits, List<String> evidenceRefs) {
        public Observation {
            requireText(workUnitId,"observation work unit"); requireText(repositoryId,"observation repository");
            evidenceRefs=List.copyOf(evidenceRefs); if (observedAtEpochMillis<0 || costUnits<0) throw new IllegalArgumentException("invalid observation");
        }
    }
    public record Snapshot(int total, int succeeded, int failed, int blocked, int unknown,
                           int stale, long costUnits, boolean trustworthy, List<String> blockers) {
        public Snapshot { blockers=List.copyOf(blockers); }
    }
    public record Forecast(long earliestDurationUnits, long likelyDurationUnits, long latestDurationUnits,
                           double confidence, List<String> assumptions) {
        public Forecast { assumptions=List.copyOf(assumptions); }
    }

    private final Map<String,Observation> observations=new HashMap<>();
    public void observe(Observation observation) {
        Observation prior=observations.get(observation.workUnitId());
        if (prior!=null && observation.observedAtEpochMillis()<prior.observedAtEpochMillis()) throw new IllegalArgumentException("stale observation update");
        observations.put(observation.workUnitId(),observation);
    }
    public Snapshot snapshot(long nowEpochMillis,long maximumAgeMillis,int expectedWorkUnits) {
        if (maximumAgeMillis<0 || expectedWorkUnits<observations.size()) throw new IllegalArgumentException("invalid control-tower scope");
        int succeeded=0,failed=0,blocked=0,unknown=expectedWorkUnits-observations.size(),stale=0; long cost=0;
        for (Observation item:observations.values()) {
            cost+=item.costUnits(); if (nowEpochMillis-item.observedAtEpochMillis()>maximumAgeMillis) stale++;
            switch(item.state()) { case SUCCEEDED -> succeeded++; case FAILED -> failed++; case BLOCKED -> blocked++; case UNKNOWN -> unknown++; default -> {} }
        }
        List<String> blockers=new ArrayList<>(); if (stale>0) blockers.add("STALE_OBSERVATIONS:"+stale); if (unknown>0) blockers.add("UNKNOWN_WORK_UNITS:"+unknown);
        return new Snapshot(expectedWorkUnits,succeeded,failed,blocked,unknown,stale,cost,blockers.isEmpty(),blockers);
    }
    public Forecast forecast(List<Long> completedDurationUnits,int remainingWorkUnits,int parallelCapacity) {
        if (remainingWorkUnits<0 || parallelCapacity<1) throw new IllegalArgumentException("invalid forecast scope");
        if (completedDurationUnits.isEmpty()) return new Forecast(0,0,Long.MAX_VALUE,0,List.of("No completed workload evidence is available."));
        List<Long> samples=completedDurationUnits.stream().sorted().toList();
        long low=samples.get(Math.max(0,(int)Math.floor((samples.size()-1)*0.1)));
        long median=samples.get((samples.size()-1)/2); long high=samples.get((int)Math.ceil((samples.size()-1)*0.9));
        long waves=(remainingWorkUnits+parallelCapacity-1L)/parallelCapacity;
        double confidence=Math.min(.95,.35+samples.size()*.06);
        return new Forecast(low*waves,median*waves,high*waves,confidence,List.of("Forecast uses observed completed-work-unit durations.","Queueing and approval time are excluded."));
    }
}
