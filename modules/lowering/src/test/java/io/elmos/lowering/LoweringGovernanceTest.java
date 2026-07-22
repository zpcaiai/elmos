package io.elmos.lowering;

import io.elmos.uir.UirModels;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.lowering.LoweringModels.*;
import static org.junit.jupiter.api.Assertions.*;

class LoweringGovernanceTest {
    @Test void nonNativeCapabilityNeedsABoundedFallback(){
        Capability unsafe=new Capability("cap:test","java","21","helper",List.of(),List.of(),List.of("gap"),List.of(),List.of());
        assertThrows(IllegalArgumentException.class,()->new TargetCapabilityMatrix(List.of(unsafe)));
    }
    @Test void productionRuleMustBeTestedAndIdempotent(){
        Rule unsafe=new Rule("rule:test","1","uir.core","call","java","21",null,"native",1,1,"exact",false,true,List.of(),List.of(),List.of(),List.of());
        assertThrows(IllegalArgumentException.class,()->new LoweringRuleRegistry(List.of(unsafe)));
    }
    @Test void equallyRankedRulesBlockInsteadOfChoosingRandomly(){
        Rule first=rule("rule:a"),second=rule("rule:b");LoweringRuleRegistry registry=new LoweringRuleRegistry(List.of(first,second));
        UirModels.Operation operation=new UirModels.Operation("op","uir.core","call",List.of(),List.of(),Map.of(),List.of(),List.of(),List.of(),new UirModels.Evaluation(List.of(),List.of(),false,true),1);
        assertThrows(IllegalStateException.class,()->registry.select(operation,"java","21",Set.of()));
    }
    private static Rule rule(String id){return new Rule(id,"1","uir.core","call","java","21",null,"native",10,10,"exact",true,true,List.of(),List.of(),List.of(),List.of("unit"));}
}
