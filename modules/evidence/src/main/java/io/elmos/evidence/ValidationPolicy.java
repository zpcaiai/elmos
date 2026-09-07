package io.elmos.evidence;

import java.util.ArrayList;
import java.util.Collection;
import java.util.EnumSet;
import java.util.List;

public final class ValidationPolicy {
    private final EnumSet<EvidenceType> required;
    public ValidationPolicy(Collection<EvidenceType> required) {
        if (required == null || required.isEmpty()) throw new IllegalArgumentException("at least one evidence type is required");
        this.required = EnumSet.copyOf(required);
    }
    public Decision evaluate(Collection<Evidence> evidence) {
        var reasons = new ArrayList<String>();
        for (var type : required) {
            var matches = evidence.stream().filter(e -> e.evidenceType() == type).toList();
            if (matches.isEmpty()) reasons.add(type + " is missing");
            else if (matches.stream().anyMatch(e -> e.status() == EvidenceStatus.FAIL)) reasons.add(type + " failed");
            else if (matches.stream().allMatch(e -> e.status() == EvidenceStatus.NOT_RUN || e.status() == EvidenceStatus.INCONCLUSIVE)) reasons.add(type + " was not conclusively run");
        }
        if (evidence.stream().anyMatch(e -> e.status() == EvidenceStatus.FAIL)) reasons.add("evidence pack contains FAIL");
        return new Decision(reasons.isEmpty(), List.copyOf(reasons));
    }
    public record Decision(boolean passed, List<String> reasons) {}
}
