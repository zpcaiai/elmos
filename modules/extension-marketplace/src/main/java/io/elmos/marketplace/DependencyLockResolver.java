package io.elmos.marketplace;

import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import static io.elmos.marketplace.MarketplaceModels.*;

public final class DependencyLockResolver {
    public PolicyDecision validate(List<Dependency> dependencies) {
        Map<String,Dependency> byId=new HashMap<>();
        for (Dependency item:dependencies) {
            if (byId.put(item.extensionId(),item)!=null) return PolicyDecision.deny("DUPLICATE_DEPENDENCY");
            if (item.revoked()) return PolicyDecision.deny("REVOKED_DEPENDENCY");
            if (item.version().contains("*") || item.version().equalsIgnoreCase("latest") || !Digests.exact(item.digest())) return PolicyDecision.deny("FLOATING_OR_UNPINNED_DEPENDENCY");
        }
        for (Dependency item:dependencies) for (String target:item.dependsOn()) if (!byId.containsKey(target)) return PolicyDecision.deny("DEPENDENCY_TARGET_MISSING");
        Set<String> complete=new HashSet<>(), visiting=new HashSet<>();
        for (String id:byId.keySet()) if (cycle(id,byId,visiting,complete)) return PolicyDecision.deny("DEPENDENCY_CYCLE");
        return PolicyDecision.allow("DEPENDENCY_LOCK_VALID","nodes:"+dependencies.size());
    }
    private boolean cycle(String id,Map<String,Dependency> nodes,Set<String> visiting,Set<String> complete) {
        if (complete.contains(id)) return false; if (!visiting.add(id)) return true;
        for (String child:nodes.get(id).dependsOn()) if (cycle(child,nodes,visiting,complete)) return true;
        visiting.remove(id); complete.add(id); return false;
    }
}
