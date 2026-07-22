package io.elmos.lowering;

import java.util.*;

import static io.elmos.lowering.LoweringModels.Capability;

/** Version-bound capability facts. A missing or unsupported fact blocks automatic lowering. */
public final class TargetCapabilityMatrix {
    private static final Set<String> LANGUAGES = Set.of("java", "python", "csharp", "typescript", "javascript");
    private final Map<String, Capability> capabilities;

    public TargetCapabilityMatrix(Collection<Capability> values) {
        Map<String, Capability> indexed = new TreeMap<>();
        for (Capability value : values) {
            if (!LANGUAGES.contains(value.targetLanguage())) throw new IllegalArgumentException("CAPABILITY_LANGUAGE_UNSUPPORTED");
            if (value.targetVersion()==null || value.targetVersion().isBlank()) throw new IllegalArgumentException("CAPABILITY_VERSION_REQUIRED");
            String key=key(value.targetLanguage(), value.targetVersion(), value.capabilityId());
            if (indexed.put(key,value)!=null) throw new IllegalArgumentException("CAPABILITY_DUPLICATE:"+key);
            if (!value.state().equals("native") && value.fallbacks().isEmpty() && !value.state().equals("unsupported"))
                throw new IllegalArgumentException("CAPABILITY_FALLBACK_REQUIRED:"+value.capabilityId());
        }
        capabilities=Map.copyOf(indexed);
    }
    public Optional<Capability> find(String language,String version,String capabilityId){return Optional.ofNullable(capabilities.get(key(language,version,capabilityId)));}
    public Capability require(String language,String version,String capabilityId){return find(language,version,capabilityId).orElseThrow(()->new IllegalStateException("TARGET_CAPABILITY_MISSING:"+capabilityId));}
    public List<Capability> forTarget(String language,String version){return capabilities.values().stream().filter(value->value.targetLanguage().equals(language)&&value.targetVersion().equals(version)).sorted(Comparator.comparing(Capability::capabilityId)).toList();}

    public static TargetCapabilityMatrix core(String version) {
        List<Capability> values=new ArrayList<>();
        for(String language:LANGUAGES){
            values.add(nativeCapability("cap:core-control-flow",language,version,List.of("if","loop","return","throw"),List.of("lowering.core.control."+language)));
            values.add(nativeCapability("cap:direct-call",language,version,List.of("call"),List.of("lowering.core.call."+language)));
            values.add(nativeCapability("cap:ordered-evaluation",language,version,List.of("temporary","short-circuit"),List.of("lowering.core.evaluation-order."+language)));
            values.add(new Capability("cap:opaque",language,version,"manual",List.of(),List.of(),List.of("source semantics unavailable"),List.of("agent","manual"),List.of()));
            values.add(new Capability("cap:dynamic",language,version,language.equals("python")||language.equals("javascript")?"native-with-constraints":"helper",List.of("bounded-dynamic-dispatch"),List.of("allowlisted targets"),List.of("runtime binding may differ"),List.of("generated-dispatch-table","manual"),List.of("lowering.dynamic.bounded."+language)));
        }
        return new TargetCapabilityMatrix(values);
    }
    private static Capability nativeCapability(String id,String language,String version,List<String> constructs,List<String> rules){return new Capability(id,language,version,"native",constructs,List.of(),List.of(),List.of(),rules);}
    private static String key(String language,String version,String capability){return language+"\u0000"+version+"\u0000"+capability;}
}
