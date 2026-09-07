package io.elmos.evidence;

import java.time.Instant;
import java.util.Objects;

public record AuditEvent(String auditId, String actorType, String actorId, String action, String resourceType,
                         String resourceId, String beforeHash, String afterHash, Instant timestamp,
                         String requestId, String runnerId, String policyDecision, String result) {
    public AuditEvent { Objects.requireNonNull(timestamp); require(auditId,"auditId"); require(actorType,"actorType"); require(actorId,"actorId"); require(action,"action"); require(resourceType,"resourceType"); require(resourceId,"resourceId"); require(requestId,"requestId"); require(policyDecision,"policyDecision"); require(result,"result"); }
    private static void require(String value,String field){if(value==null||value.isBlank())throw new IllegalArgumentException(field+" is required");}
}

