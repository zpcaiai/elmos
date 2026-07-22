package io.elmos.developerworkflow;

import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class TelemetryPrivacyFilter {
    private final Set<String> allowedEvents;
    private final Set<String> allowedFields;

    public TelemetryPrivacyFilter(Set<String> allowedEvents, Set<String> allowedFields) {
        this.allowedEvents=Set.copyOf(allowedEvents); this.allowedFields=Set.copyOf(allowedFields);
    }

    public TelemetryResult filter(String event, Map<String,String> fields, boolean consented) {
        if (!consented) return denied("TELEMETRY_CONSENT_REQUIRED");
        if (!allowedEvents.contains(event)) return denied("EVENT_NOT_ALLOWLISTED");
        Map<String,String> accepted=new LinkedHashMap<>();
        for (var entry:fields.entrySet()) {
            String key=entry.getKey().toLowerCase(Locale.ROOT); String value=entry.getValue();
            if (key.matches(".*(source|code|prompt|secret|token|review.comment|employee|productivity).*")) return denied("FORBIDDEN_TELEMETRY_FIELD");
            if (!allowedFields.contains(entry.getKey())) return denied("FIELD_NOT_ALLOWLISTED");
            if (looksAbsolute(value)) return denied("ABSOLUTE_PATH_FORBIDDEN");
            accepted.put(entry.getKey(),value);
        }
        return new TelemetryResult(Decision.ALLOW,"TELEMETRY_ACCEPTED",accepted);
    }
    private static boolean looksAbsolute(String value) {
        if (value==null || value.isBlank()) return false;
        try { return Path.of(value).isAbsolute(); } catch (RuntimeException ignored) { return false; }
    }
    private static TelemetryResult denied(String code) { return new TelemetryResult(Decision.DENY,code,Map.of()); }
}
