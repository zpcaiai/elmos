package io.elmos.workspaceservice;

import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class SandboxImageDefinitionTest {
    @Test void allRuntimeImagesAreDigestPinnedNonRootAndUnapprovedUntilEvidenceExists() throws Exception {
        Path root = Path.of(System.getProperty("basedir"), "..", "..", "sandbox", "images").normalize();
        for (int java : new int[]{8, 11, 17, 21}) {
            String dockerfile = Files.readString(root.resolve("java" + java).resolve("Dockerfile"));
            assertTrue(dockerfile.lines().findFirst().orElseThrow().matches("FROM .+@sha256:[0-9a-f]{64}"));
            assertTrue(dockerfile.contains("USER 10001:10001")); assertFalse(dockerfile.contains("ARG TOKEN"));
        }
        String proxy = Files.readString(Path.of(System.getProperty("basedir"), "..", "egress-proxy", "Dockerfile").normalize());
        assertTrue(proxy.lines().filter(line -> line.startsWith("FROM ")).allMatch(line -> line.matches("FROM .+@sha256:[0-9a-f]{64}(?: AS build)?")));
        assertTrue(proxy.contains("USER 10001:10001")); assertFalse(proxy.contains("ARG TOKEN"));
        String agentGateway = Files.readString(Path.of(System.getProperty("basedir"), "..", "agent-gateway", "Dockerfile").normalize());
        assertTrue(agentGateway.lines().filter(line -> line.startsWith("FROM ")).allMatch(line -> line.matches("FROM .+@sha256:[0-9a-f]{64}(?: AS build)?")));
        assertTrue(agentGateway.contains("USER 10001:10001")); assertFalse(agentGateway.contains("ARG TOKEN"));
        for (String app : new String[]{"enterprise-control", "commercial-api"}) {
            String dockerfile = Files.readString(Path.of(System.getProperty("basedir"), "..", app, "Dockerfile").normalize());
            assertTrue(dockerfile.lines().filter(line -> line.startsWith("FROM ")).allMatch(line -> line.matches("FROM .+@sha256:[0-9a-f]{64}(?: AS build)?")));
            assertTrue(dockerfile.contains("USER 10001:10001")); assertFalse(dockerfile.contains("ARG TOKEN"));
        }
        String manifest = Files.readString(root.resolve("image-manifest.json"));
        assertEquals(16, manifest.split("\"approvalStatus\": \"UNAPPROVED\"", -1).length - 1);
        assertTrue(manifest.contains("dotnet-modern-linux"));
        assertTrue(manifest.contains("dotnet-modern-windows"));
        assertTrue(manifest.contains("dotnet-windows-legacy"));
        for (String profile : new String[]{"python-legacy-linux", "python-modern-cpu", "python-modern-gpu", "python-windows", "python-notebook"}) {
            assertTrue(manifest.contains(profile));
        }
        for (String image : new String[]{"python2-legacy", "python314", "python314-gpu", "python-notebook"}) {
            String dockerfile = Files.readString(Path.of(System.getProperty("basedir"), "..", "..", "sandbox-images", image, "Dockerfile").normalize());
            assertTrue(dockerfile.lines().filter(line -> line.startsWith("FROM ")).allMatch(line -> line.matches("FROM .+@sha256:[0-9a-f]{64}(?: AS uv)?")));
            assertTrue(dockerfile.contains("USER 10001:10001"));
            assertFalse(dockerfile.contains("ARG TOKEN"));
        }
        String pythonWindows = Files.readString(Path.of(System.getProperty("basedir"), "..", "..", "sandbox-images", "python-windows", "Dockerfile").normalize());
        assertTrue(pythonWindows.lines().filter(line -> line.startsWith("FROM ")).allMatch(line -> line.matches("FROM .+@sha256:[0-9a-f]{64}")));
        assertTrue(pythonWindows.contains("USER ContainerUser"));
    }
}
