package io.elmos.skeleton;

import io.elmos.uir.UirModels;

import java.util.*;

import static io.elmos.skeleton.SkeletonModels.*;

public final class SkeletonPlanner {
    private static final Set<String> LANGUAGES = Set.of("java","python","csharp","typescript","javascript");
    private static final Set<String> CALLABLES = Set.of("method","function","constructor","operator","delegate","callable");

    public Plan plan(UirModels.Dataset uir, UirModels.ConformanceReport report, TargetProfile profile) {
        Objects.requireNonNull(uir); Objects.requireNonNull(report); validate(profile);
        Set<String> eligible = new TreeSet<>(); report.modules().stream().filter(UirModels.ModuleGate::eligibleForSkeletonGeneration).forEach(gate -> eligible.add(gate.moduleId()));
        if (eligible.isEmpty()) throw new IllegalStateException("NO_UIR_MODULE_ELIGIBLE_FOR_SKELETON");
        String generation = SkeletonIds.id("generation", uir.manifest().uirRunId(), profile.targetProfileId(), profile);
        List<StackDecision> decisions = decisions(profile); List<ModuleMapping> modules = new ArrayList<>(); List<TargetProject> projects = new ArrayList<>();
        Map<String,String> moduleTargets = new HashMap<>();
        for (UirModels.Module module : payloads(uir, UirModels.Module.class).stream().filter(value -> eligible.contains(value.moduleId())).sorted(Comparator.comparing(UirModels.Module::moduleId)).toList()) {
            String target = "target-module:" + safeModule(module.projectId()); moduleTargets.put(module.moduleId(), target);
            modules.add(new ModuleMapping(SkeletonIds.id("module-map", module.moduleId(), target), List.of(module.moduleId()), target, "one-to-one", "library", List.of("preserve source module responsibility"), List.of(), "faithful-port", "medium", List.of("default preserves boundaries; review before merge or split")));
            projects.add(project(target, profile));
        }
        List<NamingMapping> names = new ArrayList<>(); List<Placeholder> placeholders = new ArrayList<>(); List<TargetMapping> mappings = new ArrayList<>(); Set<String> caseFolded = new HashSet<>();
        Map<String,List<String>> obligations = new HashMap<>(); for (UirModels.Obligation obligation : payloads(uir,UirModels.Obligation.class)) if (obligation.declarationId()!=null) obligations.computeIfAbsent(obligation.declarationId(),ignored->new ArrayList<>()).add(obligation.obligationId());
        for (UirModels.Declaration declaration : payloads(uir,UirModels.Declaration.class).stream().filter(value -> moduleTargets.containsKey(moduleOf(uir,value.declarationId()))).sorted(Comparator.comparing(UirModels.Declaration::declarationId)).toList()) {
            String targetModule = moduleTargets.get(moduleOf(uir,declaration.declarationId())), name = targetName(declaration.name(), profile.language());
            String qualified = qualified(targetModule,name,profile.language()), targetId = SkeletonIds.id("targetdecl", profile.targetProfileId(), targetModule, qualified, declaration.typeId());
            String file = sourcePath(targetModule,name,profile.language()); String collision = caseFolded.add(file.toLowerCase(Locale.ROOT)) ? "none" : "case-folding";
            List<String> obligationIds = obligations.getOrDefault(declaration.declarationId(),List.of());
            names.add(new NamingMapping(declaration.declarationId(),targetId,declaration.qualifiedName(),qualified,file,"module-and-target-convention",collision,obligationIds));
            boolean callable = CALLABLES.contains(declaration.kind()); if (callable) placeholders.add(new Placeholder(SkeletonIds.id("placeholder",targetId),declaration.declarationId(),"throw-not-implemented","body-not-generated-batch-4",true,obligationIds));
            mappings.add(new TargetMapping(SkeletonIds.id("target-map",declaration.declarationId(),targetId),declaration.sourceSymbolIds(),List.of(declaration.declarationId()),List.of(targetId),"skeleton",generation,1,callable,null));
        }
        return new Plan(profile,decisions,modules, names,projects,placeholders,mappings,generation);
    }
    private static void validate(TargetProfile profile) { Objects.requireNonNull(profile); if (!LANGUAGES.contains(profile.language())) throw new IllegalArgumentException("TARGET_LANGUAGE_UNSUPPORTED"); if (profile.resolvedRuntimeVersion()==null || profile.resolvedRuntimeVersion().isBlank()) throw new IllegalArgumentException("TARGET_RUNTIME_UNRESOLVED"); if (!profile.unresolvedDecisions().isEmpty()) throw new IllegalStateException("TARGET_PROFILE_HAS_UNRESOLVED_DECISIONS"); Set<String> conflict=new HashSet<>(profile.approvedDependencies()); conflict.retainAll(profile.prohibitedDependencies()); if(!conflict.isEmpty()) throw new IllegalStateException("TARGET_DEPENDENCY_POLICY_CONFLICT:"+conflict); }
    private static List<StackDecision> decisions(TargetProfile profile) { String build = profile.preferredBuildTool()==null ? switch(profile.language()){case"java"->"maven";case"python"->"pyproject";case"csharp"->"msbuild";default->"npm";} : profile.preferredBuildTool(); String test=switch(profile.language()){case"java"->"junit";case"python"->"pytest";case"csharp"->"xunit";default->"vitest";}; return List.of(decision("runtime",profile.resolvedRuntimeVersion(),profile),decision("build-tool",build,profile),decision("test-framework",test,profile)); }
    private static StackDecision decision(String category,String selected,TargetProfile profile){return new StackDecision(SkeletonIds.id("stack-decision",profile.targetProfileId(),category,selected),category,selected,List.of(),List.of(profile.preferredBuildTool()==null?"ELMOS stable target default":"explicit target preference"),profile.hardConstraints(),List.of(),.8,"automatic");}
    private static TargetProject project(String id,TargetProfile profile){String build=profile.preferredBuildTool()==null?switch(profile.language()){case"java"->"maven";case"python"->"pyproject";case"csharp"->"msbuild";default->"npm";}:profile.preferredBuildTool();List<List<String>> commands=switch(profile.language()){case"java"->List.of(List.of("mvn","-o","test","-DskipTests"));case"python"->List.of(List.of("python","-m","compileall","src"));case"csharp"->List.of(List.of("dotnet","build","--no-restore"));default->List.of(List.of("npm","run","build","--if-present"));};List<List<String>> discovery=switch(profile.language()){case"java"->List.of(List.of("mvn","test","-DskipTests"));case"python"->List.of(List.of("pytest","--collect-only"));case"csharp"->List.of(List.of("dotnet","test","--list-tests"));default->List.of(List.of("npm","test","--","--listTests"));};return new TargetProject(id,"library",profile.language(),build,List.of("src"),List.of("tests"),List.of("resources"),List.of(),List.of(),Map.of("runtime",profile.resolvedRuntimeVersion(),"offline",String.valueOf(profile.offlineBuildRequired())),commands,discovery);}
    private static String moduleOf(UirModels.Dataset dataset,String declaration){return dataset.entities().stream().filter(entity->entity.entityId().equals(declaration)).map(UirModels.Entity::moduleId).findFirst().orElse(null);}
    private static String safeModule(String source){String value=source.replaceAll("[^A-Za-z0-9]+","-").replaceAll("(^-|-$)","").toLowerCase(Locale.ROOT);return value.isBlank()?"module":value;}
    private static String targetName(String source,String language){String[] parts=source.replaceAll("[^A-Za-z0-9]+"," ").trim().split(" +");StringBuilder pascal=new StringBuilder();for(String part:parts)if(!part.isBlank())pascal.append(Character.toUpperCase(part.charAt(0))).append(part.substring(1));String value=pascal.length()==0?"Generated":pascal.toString();if(language.equals("python"))return value.replaceAll("([a-z0-9])([A-Z])","$1_$2").toLowerCase(Locale.ROOT);return value;}
    private static String qualified(String module,String name,String language){String base=module.substring("target-module:".length()).replace('-','.');return language.equals("python")?base.replace('.','_')+"."+name:"Generated."+Arrays.stream(base.split("\\.")).map(value->Character.toUpperCase(value.charAt(0))+value.substring(1)).reduce((a,b)->a+"."+b).orElse("Module")+"."+name;}
    private static String sourcePath(String module,String name,String language){String base=module.substring("target-module:".length());return switch(language){case"java"->"src/main/java/generated/"+base.replace('-','/')+"/"+name+".java";case"csharp"->"src/"+base+"/"+name+".cs";case"python"->"src/"+base.replace('-','_')+"/"+name+".py";default->"src/"+base+"/"+name+".ts";};}
    private static <T>List<T>payloads(UirModels.Dataset dataset,Class<T>type){return dataset.entities().stream().map(UirModels.Entity::payload).filter(type::isInstance).map(type::cast).toList();}
}
