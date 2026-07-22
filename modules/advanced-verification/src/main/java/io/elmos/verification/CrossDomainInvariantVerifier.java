package io.elmos.verification;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

import static io.elmos.verification.VerificationModels.*;

public final class CrossDomainInvariantVerifier {
    public record DeniedActionObservation(String scenarioId,boolean denied,String stateBeforeDigest,
                                          String stateAfterDigest,String authorizedTenant,String observedTenant) {}

    public TechniqueResult verifyConservation(String invariantId,List<BigDecimal> before,List<BigDecimal> after) {
        if (before.isEmpty()||after.isEmpty()) throw new IllegalArgumentException("conservation datasets are required");
        BigDecimal beforeTotal=before.stream().reduce(BigDecimal.ZERO,BigDecimal::add);
        BigDecimal afterTotal=after.stream().reduce(BigDecimal.ZERO,BigDecimal::add);
        List<Counterexample> failures=beforeTotal.compareTo(afterTotal)==0?List.of():List.of(CounterexampleFactory.create(
                "invariant",invariantId,0,beforeTotal,afterTotal,"CONSERVATION_VIOLATED"));
        return result("invariant",invariantId,failures,before.size()+after.size(),Map.of("before_total",beforeTotal,"after_total",afterTotal));
    }

    public TechniqueResult verifyDeniedActions(String propertyId,List<DeniedActionObservation> observations) {
        if (observations.isEmpty()) throw new IllegalArgumentException("denied-action observations are required");
        List<Counterexample> failures=new ArrayList<>(); int executed=0;
        for (DeniedActionObservation observation:observations) {
            executed++; String code=null;
            if (!observation.denied()) code="ACTION_NOT_DENIED";
            else if (!observation.stateBeforeDigest().equals(observation.stateAfterDigest())) code="DENIED_ACTION_SIDE_EFFECT";
            else if (!observation.authorizedTenant().equals(observation.observedTenant())) code="TENANT_NONINTERFERENCE_VIOLATED";
            if (code!=null) { failures.add(CounterexampleFactory.create("security",propertyId,0,observation,observation,code)); break; }
        }
        return result("security",propertyId,failures,executed,Map.of("cases",executed));
    }

    public TechniqueResult verifyCanonicalQueryRows(String propertyId,List<Map<String,Object>> source,List<Map<String,Object>> target) {
        List<String> left=canonical(source),right=canonical(target); List<Counterexample> failures=left.equals(right)?List.of():List.of(
                CounterexampleFactory.create("query",propertyId,0,left,right,"CANONICAL_ROWS_DIFFER"));
        return result("query",propertyId,failures,Math.max(source.size(),target.size()),Map.of("source_rows",source.size(),"target_rows",target.size()));
    }

    private static List<String> canonical(List<Map<String,Object>> rows) {
        return rows.stream().map(row->row.entrySet().stream().sorted(Map.Entry.comparingByKey())
                .map(entry->entry.getKey()+"="+String.valueOf(entry.getValue())).reduce("",(a,b)->a+"\0"+b))
                .sorted(Comparator.naturalOrder()).toList();
    }
    private static TechniqueResult result(String technique,String id,List<Counterexample> failures,int cases,Map<String,Number> metrics) {
        return new TechniqueResult(technique,id,failures.isEmpty()?Status.PASS:Status.FAIL,cases,1,failures,List.of(),List.of("local://"+technique+"/"+id),metrics);
    }
}
