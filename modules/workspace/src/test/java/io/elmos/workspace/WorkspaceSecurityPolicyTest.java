package io.elmos.workspace;

import org.junit.jupiter.api.Test;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class WorkspaceSecurityPolicyTest {
    @Test void producesFailClosedContainerSpecification() {
        var limits = new WorkspaceModels.ResourceLimits(2, 4096, 512, 10240, Duration.ofMinutes(30));
        var request = new WorkspaceModels.WorkspaceRequest("ws-1", "org-1", "run-1", "snapshot-1", "java21-maven",
                "sha256:" + "a".repeat(64), limits, "offline-v1", "corr-1");
        var spec = new WorkspaceSecurityPolicy().specification(request);
        assertEquals("10001:10001", spec.user()); assertTrue(spec.readOnlyRoot()); assertFalse(spec.privileged());
        assertEquals(List.of("ALL"), spec.capDrop()); assertTrue(spec.securityOptions().contains("no-new-privileges:true"));
        assertEquals(spec.memoryBytes(), spec.memorySwapBytes()); assertTrue(spec.internalNetwork()); assertFalse(spec.hostNetwork());
        assertTrue(spec.mounts().stream().filter(m -> m.containerPath().equals("/input/snapshot")).allMatch(WorkspaceSecurityPolicy.Mount::readOnly));
        assertTrue(spec.tmpfs().containsKey("/run/secrets"));
    }

    @Test void validatesArgvWorkingDirectoryAndEnvironment() {
        var policy = new WorkspaceSecurityPolicy();
        policy.validateCommand(new WorkspaceModels.WorkspaceCommand("c1", List.of("mvn", "-o", "test"), "/workspace/repository", Map.of("LANG", "C.UTF-8"), Duration.ofMinutes(5)));
        assertThrows(SecurityException.class, () -> policy.validateCommand(new WorkspaceModels.WorkspaceCommand("c2", List.of("sh", "-c", "curl evil"), "/workspace", Map.of(), Duration.ofMinutes(1))));
        assertThrows(SecurityException.class, () -> new WorkspaceModels.WorkspaceCommand("c3", List.of("mvn"), "/etc", Map.of(), Duration.ofMinutes(1)));
        assertThrows(SecurityException.class, () -> new WorkspaceModels.WorkspaceCommand("c4", List.of("mvn"), "/workspace", Map.of("TOKEN", "x"), Duration.ofMinutes(1)));
    }
}
