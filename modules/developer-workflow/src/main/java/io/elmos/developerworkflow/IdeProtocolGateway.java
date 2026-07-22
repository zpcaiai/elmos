package io.elmos.developerworkflow;

import java.nio.file.Path;
import java.util.Map;
import java.util.Set;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class IdeProtocolGateway {
    private final String protocolVersion;
    private final Set<String> allowedTools;
    private final Map<String, String> requiredPermissionByMethod;

    public IdeProtocolGateway(String protocolVersion, Set<String> allowedTools,
                              Map<String, String> requiredPermissionByMethod) {
        this.protocolVersion = protocolVersion;
        this.allowedTools = Set.copyOf(allowedTools);
        this.requiredPermissionByMethod = Map.copyOf(requiredPermissionByMethod);
    }

    public PolicyDecision authorize(ProtocolRequest request) {
        if (!protocolVersion.equals(request.protocolVersion())) return PolicyDecision.deny("PROTOCOL_VERSION_MISMATCH");
        if (blank(request.tenantId()) || blank(request.projectId())) return PolicyDecision.deny("SCOPE_REQUIRED");
        if (!Digests.exactSha256(request.artifactDigest())) return PolicyDecision.deny("ARTIFACT_DIGEST_REQUIRED");
        if (request.documentVersion() < 0) return PolicyDecision.deny("DOCUMENT_VERSION_REQUIRED");
        if (!safeRelativePath(request.workspaceRelativePath())) return PolicyDecision.deny("PATH_OUTSIDE_WORKSPACE");
        if (!allowedTools.contains(request.tool())) return PolicyDecision.deny("TOOL_NOT_ALLOWLISTED");
        String permission = requiredPermissionByMethod.get(request.method());
        if (permission == null) return PolicyDecision.deny("METHOD_NOT_ALLOWLISTED");
        if (!request.permissions().contains(permission)) return PolicyDecision.deny("PERMISSION_DENIED");
        return PolicyDecision.allow("IDE_REQUEST_AUTHORIZED", request.artifactDigest());
    }

    private static boolean safeRelativePath(String value) {
        if (blank(value)) return false;
        Path path = Path.of(value);
        return !path.isAbsolute() && !value.contains("..") && value.indexOf('\0') < 0;
    }

    private static boolean blank(String value) { return value == null || value.isBlank(); }
}
