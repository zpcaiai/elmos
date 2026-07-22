package io.elmos.network;

import java.time.Instant;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

public record NetworkPolicy(String policyId, int version, DefaultAction defaultAction, Set<String> allowedHosts, Instant expiresAt) {
    public enum DefaultAction { DENY }
    public NetworkPolicy {
        if (policyId == null || policyId.isBlank() || version < 1) throw new IllegalArgumentException("policy identity and positive version are required");
        if (defaultAction != DefaultAction.DENY) throw new IllegalArgumentException("sandbox network policy must default deny");
        TreeSet<String> normalized = new TreeSet<>();
        for (String host : allowedHosts == null ? Set.<String>of() : allowedHosts) {
            String value = host.toLowerCase(Locale.ROOT);
            if (!value.matches("(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?") || value.contains("*")) {
                throw new IllegalArgumentException("only exact DNS host names are allowed");
            }
            normalized.add(value);
        }
        allowedHosts = Set.copyOf(normalized);
    }
}
