package io.elmos.verification;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.verification.VerificationModels.*;

public final class DeterministicScheduleExplorer {
    public record Operation(String threadId,String operationId) {
        public Operation { VerificationModels.requireText(threadId,"operation thread"); VerificationModels.requireText(operationId,"operation id"); }
        @Override public String toString() { return threadId+":"+operationId; }
    }
    @FunctionalInterface public interface ScheduleExecution { String outcome(List<Operation> schedule); }

    public TechniqueResult explore(String propertyId, List<List<Operation>> threadOperations,
                                   Set<String> forbiddenOutcomes, int maximumSchedules, ScheduleExecution execution) {
        if (threadOperations.isEmpty() || maximumSchedules<1) throw new IllegalArgumentException("threads and schedule budget are required");
        List<List<Operation>> schedules=new ArrayList<>(); enumerate(threadOperations,new int[threadOperations.size()],new ArrayList<>(),schedules,maximumSchedules);
        List<Counterexample> failures=new ArrayList<>(); Set<String> outcomes=new LinkedHashSet<>();
        for (List<Operation> schedule:schedules) {
            String outcome=execution.outcome(schedule); outcomes.add(outcome);
            if (forbiddenOutcomes.contains(outcome)) {
                failures.add(CounterexampleFactory.create("concurrency",propertyId,0,schedule,schedule,"FORBIDDEN_OUTCOME:"+outcome)); break;
            }
        }
        long theoretical=countInterleavings(threadOperations,maximumSchedules+1L); boolean exhausted=theoretical>schedules.size();
        List<String> unknowns=exhausted?List.of("SCHEDULE_BUDGET_EXHAUSTED"):List.of();
        Status status=!failures.isEmpty()?Status.FAIL:unknowns.isEmpty()?Status.PASS:Status.UNKNOWN;
        return new TechniqueResult("concurrency",propertyId,status,schedules.size(),exhausted?0:schedules.isEmpty()?0:1,
                failures,unknowns,List.of("local://concurrency/"+propertyId),Map.of("schedules",schedules.size(),"outcomes",outcomes.size()));
    }

    private static void enumerate(List<List<Operation>> threads,int[] positions,List<Operation> current,List<List<Operation>> output,int maximum) {
        if (output.size()>=maximum) return; boolean complete=true;
        for (int thread=0;thread<threads.size();thread++) {
            if (positions[thread]>=threads.get(thread).size()) continue; complete=false;
            Operation operation=threads.get(thread).get(positions[thread]++); current.add(operation);
            enumerate(threads,positions,current,output,maximum); current.remove(current.size()-1); positions[thread]--;
        }
        if (complete) output.add(List.copyOf(current));
    }

    private static long countInterleavings(List<List<Operation>> threads,long cap) {
        long result=1,total=0;
        for (List<Operation> thread:threads) {
            for (int i=1;i<=thread.size();i++) { result=result*(total+i)/i; if (result>=cap) return cap; }
            total+=thread.size();
        }
        return result;
    }
}
