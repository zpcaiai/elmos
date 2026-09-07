package io.elmos.lowering;

import io.elmos.skeleton.SkeletonModels;
import io.elmos.uir.UirModels;

import java.util.*;

import static io.elmos.lowering.LoweringModels.*;

public final class LoweringPlanner {
    private static final Set<String> CALLABLES=Set.of("method","function","constructor","operator","delegate","callable");
    private final TargetCapabilityMatrix capabilities; private final LoweringRuleRegistry rules;
    public LoweringPlanner(TargetCapabilityMatrix capabilities,LoweringRuleRegistry rules){this.capabilities=Objects.requireNonNull(capabilities);this.rules=Objects.requireNonNull(rules);}

    public List<CallablePlan> plan(Request request){
        requireEligible(request); String language=request.skeleton().plan().profile().language(),version=request.skeleton().plan().profile().resolvedRuntimeVersion();
        Map<String,SkeletonModels.NamingMapping> targets=new HashMap<>();request.skeleton().plan().names().forEach(value->targets.put(value.sourceDeclarationId(),value));
        Map<String,String> targetModules=new HashMap<>();for(SkeletonModels.ModuleMapping mapping:request.skeleton().plan().modules())for(String source: mapping.sourceModuleIds())targetModules.put(source,mapping.targetModuleId());
        Map<String,UirModels.Region> regions=index(request.uir(),UirModels.Region.class,UirModels.Region::regionId);
        Map<String,UirModels.Block> blocks=index(request.uir(),UirModels.Block.class,UirModels.Block::blockId);
        Map<String,UirModels.Operation> operations=index(request.uir(),UirModels.Operation.class,UirModels.Operation::operationId);
        Map<String,UirModels.Type> types=index(request.uir(),UirModels.Type.class,UirModels.Type::typeId);
        Map<String,List<UirModels.Obligation>> obligations=new HashMap<>();for(UirModels.Obligation value:payloads(request.uir(),UirModels.Obligation.class))if(value.declarationId()!=null)obligations.computeIfAbsent(value.declarationId(),ignored->new ArrayList<>()).add(value);
        List<CallablePlan> plans=new ArrayList<>();
        for(UirModels.Declaration declaration:payloads(request.uir(),UirModels.Declaration.class).stream().filter(value->CALLABLES.contains(value.kind())&&value.bodyRegionId()!=null).sorted(Comparator.comparing(UirModels.Declaration::declarationId)).toList()){
            SkeletonModels.NamingMapping target=targets.get(declaration.declarationId());if(target==null)continue;
            List<UirModels.Operation> callableOperations=operations(declaration,regions,blocks,operations);List<String> escalation=new ArrayList<>();List<OperationPlan> operationPlans=new ArrayList<>();List<Temporary> temporaries=new ArrayList<>();
            for(UirModels.Operation operation:callableOperations){
                if(operation.opcode().equals("opaque")||operation.dialect().startsWith("uir.lang.")){capabilities.require(language,version,"cap:opaque");escalation.add("opaque-operation:"+operation.operationId());continue;}
                if(operation.dialect().equals("uir.dynamic")){Capability capability=capabilities.require(language,version,"cap:dynamic");if(!capability.state().equals("native"))escalation.add("dynamic-operation:"+operation.operationId());continue;}
                capabilities.require(language,version,operation.opcode().equals("return")?"cap:core-control-flow":"cap:direct-call");
                Optional<Rule> selected=rules.select(operation,language,version,new HashSet<>(request.skeleton().plan().profile().approvedDependencies()));
                if(selected.isEmpty()){escalation.add("no-rule:"+operation.operationId());continue;}Rule rule=selected.get();
                List<String> temporaryIds=new ArrayList<>();if(needsTemporary(operation)){
                    String id=LoweringIds.id("temp",target.targetDeclarationId(),operation.operationId());temporaries.add(new Temporary(id,"migrationTemp"+temporaries.size(),operation.results().isEmpty()?null:operation.results().getFirst().typeId(),List.of(operation.operationId()),declaration.bodyRegionId(),"preserve-evaluation-order"));temporaryIds.add(id);
                }
                operationPlans.add(new OperationPlan(operation.operationId(),rule.ruleId(),rule.strategy(),rule.fidelity(),operation.evaluation()==null?List.of():operation.evaluation().operandOrder(),operation.evaluation()==null?List.of():operation.evaluation().lazyOperands(),temporaryIds,List.of(LoweringIds.id("targetnode",target.targetDeclarationId(),operation.operationId())),rule.obligations(),operation.confidence()));
            }
            List<String> open=obligations.getOrDefault(declaration.declarationId(),List.of()).stream().filter(value->!Set.of("verified","waived").contains(value.status())).map(UirModels.Obligation::obligationId).sorted().toList();
            TypeMapping typeMapping=mapType(types.get(declaration.typeId()),language,declaration.visibility(),open);if(typeMapping.lossiness().equals("blocking"))escalation.add("public-type-mapping-blocked:"+declaration.typeId());
            String status=escalation.isEmpty()&&operationPlans.size()==callableOperations.size()?"planned":request.profile().allowAgentFallback()?"agent-required":"manual-required";
            String ruleHash=LoweringIds.hash(operationPlans.stream().map(OperationPlan::ruleId).toList());String inputHash=LoweringIds.hash(List.of(request.uir().manifest().uirRunId(),declaration,callableOperations,request.skeleton().plan().generationId(),request.profile()));
            String sourceModule=moduleOf(request.uir(),declaration.declarationId()),targetModule=targetModules.get(sourceModule);if(targetModule==null)throw new IllegalStateException("TARGET_MODULE_MAPPING_MISSING:"+sourceModule);
            plans.add(new CallablePlan(LoweringIds.id("lowerplan",target.targetDeclarationId(),inputHash,ruleHash),targetModule,declaration.declarationId(),target.targetDeclarationId(),target.targetFile(),language,status,callableOperations.stream().map(UirModels.Operation::operationId).toList(),operationPlans,List.of(typeMapping),temporaries,open,escalation,inputHash,ruleHash));
        }
        return plans.stream().sorted(Comparator.comparing(CallablePlan::callablePlanId)).toList();
    }
    private static void requireEligible(Request request){Objects.requireNonNull(request);if(request.skeleton().conformance().batch()!=4||!request.skeleton().conformance().eligibleForBatch5())throw new IllegalStateException("BATCH_4_GATE_NOT_PASSED");if(request.uirConformance().batch()!=3||request.uirConformance().status().equals("failed"))throw new IllegalStateException("UIR_CONFORMANCE_NOT_PASSED");if(request.budgets().maxAgentCalls()<0||request.budgets().maxGeneratedLocPerPatch()<1||request.budgets().maxRuleIterations()<1)throw new IllegalArgumentException("LOWERING_BUDGET_INVALID");if(request.profile().idiomaticLevel()<0||request.profile().idiomaticLevel()>2)throw new IllegalArgumentException("BATCH_5_IDIOMATIC_LEVEL_UNSUPPORTED");}
    private static List<UirModels.Operation> operations(UirModels.Declaration declaration,Map<String,UirModels.Region> regions,Map<String,UirModels.Block> blocks,Map<String,UirModels.Operation> operations){UirModels.Region region=regions.get(declaration.bodyRegionId());if(region==null)return List.of();List<UirModels.Operation> result=new ArrayList<>();Set<String>seen=new HashSet<>();for(String blockId:region.blockIds()){UirModels.Block block=blocks.get(blockId);if(block==null)continue;for(String id:block.operationIds())if(seen.add(id)&&operations.containsKey(id))result.add(operations.get(id));}return List.copyOf(result);}
    private static boolean needsTemporary(UirModels.Operation operation){if(operation.evaluation()==null||operation.operands().size()<2)return false;return !operation.effectIds().isEmpty()||operation.evaluation().shortCircuit()||!operation.evaluation().lazyOperands().isEmpty();}
    private static TypeMapping mapType(UirModels.Type type,String language,String visibility,List<String> obligations){if(type==null||Set.of("unknown","unresolved","error","dynamic").contains(type.kind()))return new TypeMapping(type==null?"missing":type.typeId(),language,null,"manual",visibility.equals("public")?"blocking":"unknown",false,obligations);String name=type.name()==null?"GeneratedType":type.name();String syntax=switch(language){case"python"->name;case"typescript","javascript"->name;default->name;};if(type.numeric()!=null&&type.numeric().category().equals("decimal"))syntax=switch(language){case"java"->"java.math.BigDecimal";case"python"->"decimal.Decimal";case"csharp"->"decimal";default->"Decimal";};return new TypeMapping(type.typeId(),language,syntax,"native","none",false,obligations);}
    private static String moduleOf(UirModels.Dataset dataset,String id){return dataset.entities().stream().filter(value->value.entityId().equals(id)).map(UirModels.Entity::moduleId).findFirst().orElseThrow();}
    private static <T>List<T>payloads(UirModels.Dataset dataset,Class<T>type){return dataset.entities().stream().map(UirModels.Entity::payload).filter(type::isInstance).map(type::cast).toList();}
    private static <T>Map<String,T>index(UirModels.Dataset dataset,Class<T>type,java.util.function.Function<T,String>id){Map<String,T>result=new HashMap<>();for(T value:payloads(dataset,type))result.put(id.apply(value),value);return result;}
}
