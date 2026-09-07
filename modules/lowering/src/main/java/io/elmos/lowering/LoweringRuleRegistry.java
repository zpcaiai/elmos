package io.elmos.lowering;

import io.elmos.uir.UirModels;

import java.util.*;

import static io.elmos.lowering.LoweringModels.Rule;

/** Deterministic, conflict-detecting registry. It never chooses randomly between equally ranked rules. */
public final class LoweringRuleRegistry {
    private final List<Rule> rules;
    public LoweringRuleRegistry(Collection<Rule> rules) {
        Map<String,Rule> ids=new HashMap<>();
        for(Rule rule:rules){
            if(ids.put(rule.ruleId()+"@"+rule.version(),rule)!=null)throw new IllegalArgumentException("LOWERING_RULE_DUPLICATE:"+rule.ruleId());
            if(rule.production()&&(rule.tests().isEmpty()||!rule.idempotent()))throw new IllegalArgumentException("PRODUCTION_RULE_NOT_TESTED_OR_IDEMPOTENT:"+rule.ruleId());
        }
        this.rules=rules.stream().sorted(Comparator.comparing(Rule::ruleId).thenComparing(Rule::version)).toList();
    }
    public Optional<Rule> select(UirModels.Operation operation,String language,String version,Set<String> approvedDependencies){
        List<Rule> candidates=rules.stream().filter(rule->rule.targetLanguage().equals(language))
                .filter(rule->rule.dialect().equals(operation.dialect())||rule.dialect().equals("*"))
                .filter(rule->rule.opcode().equals(operation.opcode())||rule.opcode().equals("*"))
                .filter(rule->versionAllowed(version,rule.minVersion(),rule.maxVersion()))
                .filter(rule->approvedDependencies.containsAll(rule.approvedDependencies()))
                .sorted(Comparator.comparingInt(Rule::specificity).reversed().thenComparing(Comparator.comparingInt(Rule::priority).reversed()).thenComparing(Rule::fidelity).thenComparing(Rule::ruleId)).toList();
        if(candidates.isEmpty())return Optional.empty();
        Rule first=candidates.getFirst();
        if(candidates.size()>1){Rule second=candidates.get(1);if(first.specificity()==second.specificity()&&first.priority()==second.priority()&&first.fidelity().equals(second.fidelity()))throw new IllegalStateException("LOWERING_RULE_CONFLICT:"+operation.operationId()+":"+first.ruleId()+":"+second.ruleId());}
        return Optional.of(first);
    }
    public List<Rule> all(){return rules;}
    public static LoweringRuleRegistry core(String version){
        List<Rule> rules=new ArrayList<>();
        for(String language:List.of("java","python","csharp","typescript","javascript")){
            rules.add(rule("lowering.core.return."+language,"uir.core","return",language,version,1000,1000,List.of("return-statement")));
            rules.add(rule("lowering.core.call."+language,"uir.core","call",language,version,1000,900,List.of("invocation")));
            rules.add(rule("lowering.object.virtual-call."+language,"uir.object","virtual_call",language,version,1000,900,List.of("virtual-invocation")));
            rules.add(rule("lowering.object.interface-call."+language,"uir.object","interface_call",language,version,1000,900,List.of("interface-invocation")));
        }
        return new LoweringRuleRegistry(rules);
    }
    private static Rule rule(String id,String dialect,String opcode,String language,String version,int specificity,int priority,List<String> constructs){return new Rule(id,"1.0",dialect,opcode,language,version,null,"native",specificity,priority,"exact",true,true,constructs,List.of(),List.of(),List.of("rule-unit","idempotency","source-map"));}
    private static boolean versionAllowed(String version,String min,String max){return version.compareTo(min)>=0&&(max==null||version.compareTo(max)<=0);}
}
