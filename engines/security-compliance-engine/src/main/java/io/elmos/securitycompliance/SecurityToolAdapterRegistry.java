package io.elmos.securitycompliance;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.securitycompliance.SecurityModels.*;

/** Declares adapter capabilities; it never loads scanner SDKs or executes host commands. */
public final class SecurityToolAdapterRegistry {
    private final Map<AdapterType, ToolAdapter> adapters;

    public SecurityToolAdapterRegistry() {
        var values = new EnumMap<AdapterType, ToolAdapter>(AdapterType.class);
        for (AdapterType type : AdapterType.values()) {
            boolean active = Set.of(AdapterType.DAST, AdapterType.API_SECURITY).contains(type);
            values.put(type, new ToolAdapter(type, type.name() + "_ADAPTER", "UNRESOLVED",
                    AdapterStatus.NOT_CONFIGURED, Set.of("DECLARED_TARGET"),
                    Set.of("READ_SOURCE", "READ_ARTIFACT", "READ_CONFIGURATION", "READ_METADATA", "SANDBOX_EXECUTE"),
                    active, "DENY", "UNRESOLVED", "TENANT_SCOPED_REDACTED",
                    "NORMALIZED_JSON", "EVIDENCE_REVIEW_AND_EXPIRY", "EXCLUSIONS_PARSE_ERRORS_TIMEOUTS_REQUIRED"));
        }
        adapters = Map.copyOf(values);
    }

    public Map<AdapterType, ToolAdapter> all() { return adapters; }
    public List<String> statusSummary() {
        return adapters.values().stream().map(value -> value.type() + ":" + value.status()).sorted().toList();
    }
}
