package io.elmos.cas;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * ELMOS-CAS-020. The identity of "this exact work on these exact inputs".
 *
 * <p>The key keeps its component map, not just its digest. That is what turns an unexpected miss
 * from a shrug into a one-line answer (ELMOS-CAS-042): diff the two keys and the component that
 * moved is the cause. Without it the only debugging tool is re-running the pipeline with print
 * statements, which is how over-invalidation survives for months.
 */
public record ActionKey(CasDigest digest, String tenantId, Map<String, String> components) {

    public ActionKey {
        Objects.requireNonNull(digest, "digest");
        tenantId = CasText.required(tenantId, "tenantId");
        components = Collections.unmodifiableMap(new LinkedHashMap<>(components));
    }

    /** @return component names whose values differ, in declaration order; empty when identical */
    public List<String> explainDifference(ActionKey other) {
        List<String> differing = new ArrayList<>();
        for (Map.Entry<String, String> component : components.entrySet()) {
            String mine = component.getValue();
            String theirs = other.components.get(component.getKey());
            if (!Objects.equals(mine, theirs)) {
                differing.add(component.getKey());
            }
        }
        for (String name : other.components.keySet()) {
            if (!components.containsKey(name)) {
                differing.add(name);
            }
        }
        return List.copyOf(differing);
    }

    public String shortForm() {
        return digest.hex().substring(0, 16);
    }
}
